"""
WorkBrain Pipeline — ADK CustomAgent
Proper BaseAgent implementation with AlloyDB persistence between steps.
"""
from __future__ import annotations
import json, logging, re, uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional, Any

from typing_extensions import override
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.utils.context_utils import Aclosing
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select as sa_select

from config import settings
from db.models import ActionItem, CognitiveState, DecisionLog, Meeting

logger = logging.getLogger(__name__)


class WorkBrainPipelineAgent(BaseAgent):
    model_config = {"arbitrary_types_allowed": True}
    db: Any = None
    meeting: Any = None
    progress_queue: Any = None

    async def _emit(self, step: int, total: int, message: str, status: str = "running"):
        if self.progress_queue:
            await self.progress_queue.put({
                "type": "progress",
                "step": step,
                "total": total,
                "message": message,
                "status": status,
            })
    """
    Custom ADK Agent orchestrating WorkBrain's 4-agent pipeline
    with AlloyDB AI persistence between steps.

    sub_agents order: [transcript_agent, cognitive_agent, scheduler_agent, execution_agent]
    """

    @override
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:

        db = self.db
        meeting = self.meeting
        _result = {}
        if not db or not meeting:
            logger.error("Missing db or meeting in context state")
            return

        mid = meeting.id
        transcript_agent, cognitive_agent, scheduler_agent, execution_agent = self.sub_agents

        # ── STEP 1: Transcript ────────────────────────────────────────────────
        logger.info("Step 1: transcript_agent")
        await self._emit(1, 4, "Transcript Agent — extracting action items...")
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        ctx.session.state["transcript_prompt"] = f"TODAY'S DATE: {today}\n\n{meeting.transcript}"
        t_events = []
        async with Aclosing(transcript_agent.run_async(ctx)) as agen:
            async for event in agen:
                t_events.append(event)
                yield event

        full_text = _best_text(t_events)
        logger.info(f"[transcript] full_text length: {len(full_text)}")
        action_items_saved = []
        items = _extract_action_items(full_text)

        if items:
            for item in items:
                ai = ActionItem(
                    user_id=settings.user_id, meeting_id=mid,
                    title=item.get("title", "Untitled"),
                    owner=item.get("owner", settings.user_id),
                    deadline=_parse_iso(item.get("deadline")),
                    priority=max(1, min(5, int(item.get("priority", 3)))),
                    complexity=max(1, min(5, int(item.get("complexity", 3)))),
                    duration_minutes=int(item.get("duration_minutes") or 60),
                    status="pending",
                )
                db.add(ai)
                action_items_saved.append(ai)
            await db.flush()

            # Generate Vertex AI embeddings
            try:
                import vertexai
                from vertexai.language_models import TextEmbeddingModel
                vertexai.init(project=settings.google_cloud_project, location=settings.google_cloud_location)
                emb_model = TextEmbeddingModel.from_pretrained("text-embedding-004")
                from sqlalchemy import text as sa_text
                for ai in action_items_saved:
                    try:
                        emb = list(emb_model.get_embeddings([ai.title])[0].values)
                        emb_str = "[" + ",".join(str(v) for v in emb) + "]"
                        await db.execute(sa_text(
                            f"UPDATE workbrain_schema.action_items SET embedding = '{emb_str}'::vector WHERE id = '{str(ai.id)}'"
                        ))
                        await db.flush()
                    except Exception as emb_err:
                        logger.warning(f"Embedding save failed for {ai.title}: {emb_err}")
                logger.info(f"Generated embeddings for {len(action_items_saved)} tasks")
            except Exception as e:
                logger.warning(f"Embedding generation failed: {e}")

            title_m = re.search(r'"meeting_title"\s*:\s*"([^"]{1,80})"', full_text)
            if title_m and not meeting.title:
                meeting.title = title_m.group(1)
            summary_m = re.search(r'"summary"\s*:\s*"([^"]{1,500})"', full_text)
            if summary_m:
                meeting.summary = summary_m.group(1)

        await _log(db, "transcript",
            f"Extracted {len(action_items_saved)} action items",
            f"Identified {len(action_items_saved)} action items across {len(set(a.owner for a in action_items_saved))} owners.",
            mid, {"count": len(action_items_saved)})

        # ── STEP 2: Cognitive ─────────────────────────────────────────────────
        logger.info("Step 2: cognitive_agent")
        await self._emit(2, 4, "Cognitive Agent — calculating load scores...")
        owners = list(set(a.owner for a in action_items_saved))
        tasks_by_owner = {}
        for owner in owners:
            existing = (await db.execute(
                sa_select(ActionItem).where(
                    ActionItem.user_id == settings.user_id,
                    ActionItem.owner == owner,
                    ActionItem.status.in_(["pending", "scheduled"]),
                    ActionItem.meeting_id != mid,
                )
            )).scalars().all()
            tasks_by_owner[owner] = [
                {"title": t.title, "duration_minutes": t.duration_minutes,
                 "complexity": t.complexity, "priority": t.priority,
                 "deadline": t.deadline.isoformat() if t.deadline else None}
                for t in existing
            ] + [
                {"title": a.title, "duration_minutes": a.duration_minutes,
                 "complexity": a.complexity, "priority": a.priority,
                 "deadline": a.deadline.isoformat() if a.deadline else None}
                for a in action_items_saved if a.owner == owner
            ]
            logger.info(f"[Cognitive] {owner}: {len(existing)} historical + {sum(1 for a in action_items_saved if a.owner == owner)} new tasks")

        ctx.session.state["cognitive_prompt"] = (
            f"Calculate cognitive load for each person.\n\n"
            f"Tasks by owner:\n{json.dumps(tasks_by_owner, indent=2)}\n\n"
            f"Call calculate_cognitive_load for each owner."
        )
        c_events = []
        async with Aclosing(cognitive_agent.run_async(ctx)) as agen:
            async for event in agen:
                c_events.append(event)
                yield event

        c_tools = _extract_tool_results(c_events)
        overloaded_owners, cognitive_states = [], {}
        for cog_data in c_tools.get("calculate_cognitive_load", []):
            owner = cog_data.get("owner", "unknown")
            cognitive_states[owner] = cog_data
            db.add(CognitiveState(
                user_id=settings.user_id, owner=owner,
                load_score=cog_data.get("load_score", 0.0),
                capacity=cog_data.get("capacity", 480.0),
                overload_flag=cog_data.get("overload_flag", False),
                context_switches=cog_data.get("context_switches", 0),
            ))
            await db.flush()
            if cog_data.get("overload_flag"):
                overloaded_owners.append(owner)
            await _log(db, "cognitive",
                f"{owner} at {cog_data.get('load_percentage', 0)}% capacity",
                cog_data.get("recommendation", ""), mid, cog_data)

        # ── STEP 3: Scheduler ─────────────────────────────────────────────────
        logger.info("Step 3: scheduler_agent")
        await self._emit(3, 4, "Scheduler Agent — checking APAC holidays & creating calendar events...")
        ctx.session.state["scheduler_prompt"] = (
            f"Overloaded owners (skip calendar blocks): {overloaded_owners}\n\n"
            f"Action items:\n{json.dumps([{'title': a.title, 'owner': a.owner, 'deadline': a.deadline.isoformat() if a.deadline else None, 'needs_focus_block': a.complexity >= 4 or a.duration_minutes >= 120, 'duration_minutes': a.duration_minutes} for a in action_items_saved], indent=2)}\n\n"
            f"Cognitive states:\n{json.dumps(cognitive_states, indent=2)}"
        )
        s_events = []
        async with Aclosing(scheduler_agent.run_async(ctx)) as agen:
            async for event in agen:
                s_events.append(event)
                yield event

        s_tools = _extract_tool_results(s_events)
        events_created = len(s_tools.get("create_calendar_event", []))
        for ev_data in s_tools.get("create_calendar_event", []):
            event_id = ev_data.get("event_id") or ev_data.get("id")
            if event_id:
                for ai in action_items_saved:
                    if ai.title.lower()[:20] in ev_data.get("title","").lower():
                        ai.calendar_event_id = event_id
                        break
            await _log(db, "scheduler", f"Calendar event: {ev_data.get('title','')}", f"Event scheduled.", mid, ev_data)
        for owner in overloaded_owners:
            await _log(db, "scheduler", f"Skipped calendar blocks for {owner}", f"{owner} is overloaded.", mid)

        # ── STEP 4: Execution ─────────────────────────────────────────────────
        logger.info("Step 4: execution_agent")
        await self._emit(4, 4, "Execution Agent — creating task cards & notifying Slack...")
        ctx.session.state["execution_prompt"] = (
            f"Action items:\n{json.dumps([{'title': a.title, 'owner': a.owner, 'priority': a.priority, 'deadline': a.deadline.isoformat() if a.deadline else None} for a in action_items_saved], indent=2)}\n\n"
            f"Cognitive states: {json.dumps(cognitive_states, indent=2)}\n"
            f"Overloaded owners: {overloaded_owners}\nCalendar events created: {events_created}"
        )
        e_events = []
        async with Aclosing(execution_agent.run_async(ctx)) as agen:
            async for event in agen:
                e_events.append(event)
                yield event

        e_tools = _extract_tool_results(e_events)
        tasks_created = len(e_tools.get("create_task_card", []))
        for task_data in e_tools.get("create_task_card", []):
            real_task_id = task_data.get("task_id")
            if real_task_id and not str(real_task_id).startswith("mock_"):
                for ai in action_items_saved:
                    if ai.title.lower()[:20] == task_data.get("title","").lower()[:20]:
                        ai.task_id = real_task_id
                        break
            await _log(db, "execution", f"Task card: {task_data.get('title','')}", f"Google Tasks card created. ID: {task_data.get('task_id','N/A')}.", mid, task_data)

        # ── Final ─────────────────────────────────────────────────────────────
        await _log(db, "orchestrator", "Meeting processing complete",
            f"Pipeline complete. {len(action_items_saved)} items | {events_created} events | {tasks_created} tasks | Overloaded: {overloaded_owners or 'none'}",
            mid, {"action_items_created": len(action_items_saved), "events_created": events_created, "tasks_created": tasks_created, "overloaded_owners": overloaded_owners})

        meeting.status = "processed"
        meeting.processed_at = datetime.now(timezone.utc)

        try:
            from tools.slack_tool import send_pipeline_summary
            cog_result = await db.execute(sa_select(CognitiveState).where(CognitiveState.user_id == settings.user_id).order_by(CognitiveState.calculated_at.desc()).limit(50))
            all_cog = cog_result.scalars().all()
            seen, latest_cog = set(), []
            for c in all_cog:
                if c.owner not in seen:
                    seen.add(c.owner)
                    latest_cog.append(c)
            send_pipeline_summary(
                meeting_title=meeting.title or "Meeting",
                action_items=action_items_saved,
                cognitive_states=latest_cog,
                overloaded_owners=overloaded_owners,
                events_created=events_created,
                tasks_created=tasks_created,
            )
        except Exception as e:
            logger.warning(f"Slack notification failed: {e}")

        await db.flush()
        logger.info(f"Pipeline DONE: {len(action_items_saved)} items | {events_created} events | {tasks_created} tasks")
        await self._emit(4, 4, f"Done! {len(action_items_saved)} tasks created, {events_created} calendar events", "done")
        if self.progress_queue:
            await self.progress_queue.put({"type": "done", "result": _result})
        _result = {
            "meeting_id": str(mid), "action_items_created": len(action_items_saved),
            "events_created": events_created, "tasks_created": tasks_created,
            "overloaded_owners": overloaded_owners,
        }


# ── Helpers ───────────────────────────────────────────────────────────────────
def _best_text(events: list) -> str:
    texts = []
    for event in events:
        if getattr(event, "content", None) and event.content.parts:
            for part in event.content.parts:
                if getattr(part, "text", ""):
                    texts.append(part.text)
    return max(texts, key=len) if texts else ""


def _extract_tool_results(events: list) -> dict[str, list]:
    results: dict[str, list] = {}
    for event in events:
        if not (getattr(event, "content", None) and event.content.parts):
            continue
        for part in event.content.parts:
            fn_resp = getattr(part, "function_response", None)
            if not fn_resp:
                continue
            name = getattr(fn_resp, "name", "")
            raw = getattr(fn_resp, "response", {})
            if isinstance(raw, dict) and "result" in raw:
                data = _safe_json(raw["result"])
            elif isinstance(raw, dict):
                data = raw
            else:
                data = _safe_json(str(raw))
            if data and "error" not in data:
                results.setdefault(name, []).append(data)
    return results


async def _log(db, agent, decision, reason, meeting_id=None, metadata=None):
    from db.models import DecisionLog
    entry = DecisionLog(user_id=settings.user_id, meeting_id=meeting_id, agent=agent, decision=decision, reason=reason, meta_data=metadata)
    db.add(entry)
    await db.flush()
    logger.info(f"[{agent}] {decision}")


def _extract_action_items(text: str) -> list:
    for pattern in [r'"action_items"\s*:\s*(\[.*?\])', r'\[\s*\{[^}]*"title"[^}]*"owner"[^}]*\}.*?\]']:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                group = m.group(1) if '"action_items"' in pattern else m.group(0)
                items = json.loads(group)
                if isinstance(items, list) and items:
                    return items
            except Exception:
                pass
    try:
        obj = json.loads(text.strip().strip('`').replace('json\n', '', 1).strip())
        if isinstance(obj, dict) and "action_items" in obj:
            return obj["action_items"]
    except Exception:
        pass
    return []


def _safe_json(val) -> dict:
    if isinstance(val, dict):
        return val
    try:
        result = json.loads(str(val))
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


def _parse_iso(s) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None