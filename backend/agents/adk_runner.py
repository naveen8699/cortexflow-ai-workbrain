"""
WorkBrain ADK Runner — ADK 1.3.0 compatible
Runs each of the 4 agents in sequence explicitly.
This is more reliable than relying on the orchestrator to chain sub-agents,
which in ADK 1.3.0 stops after the first transfer_to_agent call.
"""
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as adk_types
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from agents.adk_agents import (
    transcript_agent,
    cognitive_agent,
    scheduler_agent,
    execution_agent,
    root_agent,
)
from config import settings
from db.models import ActionItem, CognitiveState, DecisionLog, Meeting

logger = logging.getLogger(__name__)

async def run_meeting_pipeline_custom(db: AsyncSession, meeting: Meeting, progress_queue=None) -> dict:
    """
    Runs WorkBrain pipeline using ADK CustomAgent (BaseAgent pattern).
    Replaces the manual runner approach with proper ADK orchestration.
    """
    from google.adk import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types as adk_types
    from agents.adk_agents import workbrain_pipeline

    from agents.adk_agents import transcript_agent, cognitive_agent, scheduler_agent, execution_agent
    from agents.workbrain_pipeline_agent import WorkBrainPipelineAgent

    # Import fresh agent definitions to avoid parent agent conflicts
    from agents.adk_agents import (
        transcript_agent, scheduler_agent, execution_agent
    )
    from google.adk.agents import LlmAgent
    from agents.adk_tools import calculate_cognitive_load_tool
    from tools.alloydb_mcp import get_alloydb_mcp_toolset
    import os
    MODEL = os.environ.get("VERTEX_AI_MODEL", "gemini-2.5-flash")

    # Recreate cognitive agent fresh each time (has MCP toolset)
    fresh_cognitive = LlmAgent(
        name="cognitive_agent",
        model=MODEL,
        description="Calculates cognitive load per owner using AlloyDB MCP.",
        instruction=cognitive_agent.instruction,
        tools=[calculate_cognitive_load_tool, get_alloydb_mcp_toolset()],
        output_key="cognitive_result",
    )

    from agents.adk_tools import create_task_card_tool
    from tools.slack_mcp import get_slack_mcp_toolset

    fresh_execution = LlmAgent(
        name="execution_agent",
        model=MODEL,
        description="Creates Google Tasks cards and sends Slack MCP notifications.",
        instruction=execution_agent.instruction,
        tools=[create_task_card_tool, get_slack_mcp_toolset()],
        output_key="execution_result",
    )

    pipeline = WorkBrainPipelineAgent(
        name="workbrain_pipeline",
        description="WorkBrain CustomAgent pipeline",
        sub_agents=[
            transcript_agent.clone(),
            fresh_cognitive,
            scheduler_agent.clone(),
            fresh_execution,
        ],
        db=db,
        meeting=meeting,
        progress_queue=progress_queue,
    )

    svc = InMemorySessionService()
    session_id = f"meeting_{meeting.id}"

    await svc.create_session(
        app_name="agents",
        user_id=settings.user_id,
        session_id=session_id,
    )

    runner = Runner(
        agent=pipeline,
        app_name="agents",
        session_service=svc,
    )

    async for event in runner.run_async(
        user_id=settings.user_id,
        session_id=session_id,
        new_message=adk_types.Content(
            role="user",
            parts=[adk_types.Part(text="Process this meeting transcript.")],
        ),
    ):
        pass

    session = await svc.get_session(
        app_name="agents",
        user_id=settings.user_id,
        session_id=session_id,
    )
    # Read result directly from pipeline agent instance
    if hasattr(pipeline, "_pipeline_result") and pipeline._pipeline_result:
        return pipeline._pipeline_result
    return {
        "meeting_id": str(meeting.id),
        "action_items_created": 0,
        "events_created": 0,
        "tasks_created": 0,
        "overloaded_owners": [],
    }

_session_service = InMemorySessionService()

def _make_runner(agent):
    from google.adk.agents.context_cache_config import ContextCacheConfig
    try:
        return Runner(
            agent=agent,
            app_name="workbrain",
            session_service=_session_service,
            context_cache_config=ContextCacheConfig(
                cache_intervals=20,
                ttl_seconds=3600,
                min_tokens=1000,
            ),
        )
    except Exception:
        return Runner(agent=agent, app_name="workbrain", session_service=_session_service)

async def _run_agent(agent, session_id: str, prompt: str, session_state: dict = None) -> tuple[list, str]:
    """Run a single agent and return (events, final_response_text)."""
    import asyncio
    runner = _make_runner(agent)
    try:
        session = await _session_service.create_session(
            app_name="workbrain",
            user_id=settings.user_id,
            session_id=session_id,
        )
        if session_state and session:
            for k, v in session_state.items():
                session.state[k] = v
    except Exception:
        pass  # session may already exist

    # Retry on 429 rate limit
    max_retries = 3
    for attempt in range(max_retries):
        try:
            events = []
            final_text = ""
            async for event in runner.run_async(
                user_id=settings.user_id,
                session_id=session_id,
                new_message=adk_types.Content(
                    role="user",
                    parts=[adk_types.Part(text=prompt)],
                ),
            ):
                events.append(event)
                if hasattr(event, "is_final_response") and event.is_final_response():
                    if event.content and event.content.parts:
                        final_text = " ".join(
                            p.text for p in event.content.parts if getattr(p, "text", "")
                        )
            return events, final_text
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait_time = (attempt + 1) * 30  # 30, 60, 90 seconds
                logger.warning(f"Rate limit hit, waiting {wait_time}s before retry {attempt+1}/{max_retries}")
                await asyncio.sleep(wait_time)
                if attempt == max_retries - 1:
                    raise
            else:
                raise
    return [], ""  # Should never reach here



def _extract_tool_results(events: list) -> dict[str, list]:
    """
    Extract all tool call results from ADK 1.3.0 events.
    In ADK 1.3.0: part.function_response.response = {'result': 'json_string'}
    """
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
            # ADK 1.3.0 wraps result: {'result': 'json_string_or_value'}
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
    entry = DecisionLog(
        user_id=settings.user_id,
        meeting_id=meeting_id,
        agent=agent,
        decision=decision,
        reason=reason,
        meta_data=metadata,
    )
    db.add(entry)
    await db.flush()
    logger.info(f"[{agent}] {decision}")


async def run_meeting_pipeline(db: AsyncSession, meeting: Meeting) -> dict:
    """
    Runs 4 agents explicitly in sequence:
    transcript_agent → cognitive_agent → scheduler_agent → execution_agent
    """
    mid = meeting.id
    run_id = uuid.uuid4().hex[:6]

    # ── STEP 1: Transcript Agent ──────────────────────────────────────────────
    logger.info("Step 1: transcript_agent")
    t_events, t_text = await _run_agent(
        transcript_agent,
        f"transcript_{run_id}",
        (
            f"Extract all action items from this transcript.\n\n"
            f"IMPORTANT: Return ONLY valid JSON. No markdown, no explanation, just JSON.\n\n"
            f"=== TRANSCRIPT ===\n{meeting.transcript}\n=== END ==="
        ),
    )

    t_tools = _extract_tool_results(t_events)
    action_items_saved = []

    # Parse action items — check all event texts since agent may call tools first
    # Collect all text from all events not just final response
    all_event_texts = []
    for event in t_events:
        if getattr(event, "content", None) and event.content.parts:
            for part in event.content.parts:
                if getattr(part, "text", ""):
                    all_event_texts.append(part.text)

    # Use longest text available — Cloud Run may truncate final_text
    all_texts_combined = all_event_texts + ([t_text] if t_text else [])
    full_text = max(all_texts_combined, key=len) if all_texts_combined else ""

    logger.info(f"[transcript] full_text length: {len(full_text)}, events: {len(all_event_texts)}")

    items = _extract_action_items(full_text)
    if not items:
        # Try each event text individually
        for et in sorted(all_event_texts, key=len, reverse=True):
            items = _extract_action_items(et)
            if items:
                logger.info(f"[transcript] Found items in event text of length {len(et)}")
                break
    if items:
        for item in items:
            ai = ActionItem(
                user_id=settings.user_id,
                meeting_id=mid,
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

        # Generate Vertex AI embeddings for duplicate detection
        try:
            import vertexai
            from vertexai.language_models import TextEmbeddingModel
            vertexai.init(
                project=settings.google_cloud_project,
                location=settings.google_cloud_location
            )
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


        # Extract meeting title + summary
        title_m = re.search(r'"meeting_title"\s*:\s*"([^"]{1,80})"', full_text)
        if title_m and not meeting.title:
            meeting.title = title_m.group(1)
        summary_m = re.search(r'"summary"\s*:\s*"([^"]{1,500})"', full_text)
        if summary_m:
            meeting.summary = summary_m.group(1)

    await _log(db, "transcript",
        f"Extracted {len(action_items_saved)} action items",
        f"Identified {len(action_items_saved)} action items across "
        f"{len(set(a.owner for a in action_items_saved))} owners.",
        mid, {"count": len(action_items_saved)})

    # ── STEP 2: Cognitive Agent ───────────────────────────────────────────────
    logger.info("Step 2: cognitive_agent")
    owners = list(set(a.owner for a in action_items_saved))

    # Load existing pending tasks from DB for each owner (historical context)
    from sqlalchemy import select as sa_select
    tasks_by_owner = {}
    for owner in owners:
        # Get all existing pending/scheduled tasks for this owner
        existing_result = await db.execute(
            sa_select(ActionItem).where(
                ActionItem.user_id == settings.user_id,
                ActionItem.owner == owner,
                ActionItem.status.in_(["pending", "scheduled"]),
                ActionItem.meeting_id != mid,  # exclude current meeting tasks
            )
        )
        existing_tasks = existing_result.scalars().all()

        # Combine historical + current meeting tasks
        all_tasks = []
        for t in existing_tasks:
            all_tasks.append({
                "title": t.title,
                "duration_minutes": t.duration_minutes,
                "complexity": t.complexity,
                "priority": t.priority,
                "deadline": t.deadline.isoformat() if t.deadline else None,
                "source": "historical",
            })
        for a in action_items_saved:
            if a.owner == owner:
                all_tasks.append({
                    "title": a.title,
                    "duration_minutes": a.duration_minutes,
                    "complexity": a.complexity,
                    "priority": a.priority,
                    "deadline": a.deadline.isoformat() if a.deadline else None,
                    "source": "current_meeting",
                })
        tasks_by_owner[owner] = all_tasks
        logger.info(f"[Cognitive] {owner}: {len(existing_tasks)} historical + {sum(1 for a in action_items_saved if a.owner == owner)} new tasks")

    # Keep original format for compatibility
    for owner in owners:
        tasks_by_owner[owner] = [
            {
                "title": a["title"],
                "duration_minutes": a["duration_minutes"],
                "complexity": a["complexity"],
                "priority": a["priority"],
                "deadline": a["deadline"],
            }
            for a in tasks_by_owner[owner]
        ]

    cog_prompt = (
        f"Calculate cognitive load for each person based on their tasks.\n\n"
        f"Action items by owner:\n{json.dumps(tasks_by_owner, indent=2)}\n\n"
        f"Call calculate_cognitive_load for each owner."
    )
    c_events, c_text = await _run_agent(cognitive_agent, f"cog_{run_id}", cog_prompt)
    c_tools = _extract_tool_results(c_events)

    overloaded_owners = []
    cognitive_states = {}

    for cog_data in c_tools.get("calculate_cognitive_load", []):
        owner = cog_data.get("owner", "unknown")
        cognitive_states[owner] = cog_data
        db.add(CognitiveState(
            user_id=settings.user_id,
            owner=owner,
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
            cog_data.get("recommendation", ""),
            mid, cog_data)

    if not c_tools.get("calculate_cognitive_load"):
        # Agent responded in text without calling tool — parse from text
        await _log(db, "cognitive", "Cognitive analysis complete", c_text[:300], mid)

    # ── STEP 3: Scheduler Agent ───────────────────────────────────────────────
    logger.info("Step 3: scheduler_agent")
    sched_prompt = (
        f"Create calendar events for action items. "
        f"Overloaded owners (skip calendar blocks): {overloaded_owners}\n\n"
        f"Action items:\n{json.dumps([{'title': a.title, 'owner': a.owner, 'deadline': a.deadline.isoformat() if a.deadline else None, 'needs_focus_block': a.complexity >= 4 or a.duration_minutes >= 120, 'duration_minutes': a.duration_minutes} for a in action_items_saved], indent=2)}\n\n"
        f"Cognitive states:\n{json.dumps(cognitive_states, indent=2)}"
    )
    s_events, s_text = await _run_agent(scheduler_agent, f"sched_{run_id}", sched_prompt)
    s_tools = _extract_tool_results(s_events)

    events_created = len(s_tools.get("create_calendar_event", []))
    for ev_data in s_tools.get("create_calendar_event", []):
        # Save calendar_event_id back to matching ActionItem
        event_id = ev_data.get("event_id") or ev_data.get("id")
        event_title = ev_data.get("title", "")
        if event_id:
            for ai in action_items_saved:
                if ai.title.lower()[:20] in event_title.lower() or event_title.lower()[:20] in ai.title.lower():
                    ai.calendar_event_id = event_id
                    break
        await _log(db, "scheduler",
            f"Calendar event: {ev_data.get('title','')}",
            f"Event '{ev_data.get('title','')}' scheduled {ev_data.get('start','')} to {ev_data.get('end','')}.",
            mid, ev_data)

    for owner in overloaded_owners:
        await _log(db, "scheduler",
            f"Skipped calendar blocks for {owner}",
            f"{owner} is overloaded. No calendar blocks added. Task card still created for tracking.",
            mid)

    if not s_tools.get("create_calendar_event") and not overloaded_owners:
        await _log(db, "scheduler", "Scheduling complete", s_text[:300], mid)

    # ── STEP 4: Execution Agent ───────────────────────────────────────────────
    logger.info("Step 4: execution_agent")
    exec_prompt = (
        f"Create Google Tasks cards for ALL action items and produce a decisions summary.\n\n"
        f"Action items:\n{json.dumps([{'title': a.title, 'owner': a.owner, 'priority': a.priority, 'deadline': a.deadline.isoformat() if a.deadline else None} for a in action_items_saved], indent=2)}\n\n"
        f"Cognitive states: {json.dumps(cognitive_states, indent=2)}\n"
        f"Overloaded owners: {overloaded_owners}\n"
        f"Calendar events created: {events_created}"
    )
    e_events, e_text = await _run_agent(execution_agent, f"exec_{run_id}", exec_prompt)
    e_tools = _extract_tool_results(e_events)

    tasks_created = len(e_tools.get("create_task_card", []))
    for task_data in e_tools.get("create_task_card", []):
        # Save real task_id back to ActionItem record
        real_task_id = task_data.get("task_id")
        if real_task_id and not real_task_id.startswith("mock_"):
            from sqlalchemy import select as sa_select2
            title_match = task_data.get("title", "")
            for ai in action_items_saved:
                if ai.title.lower()[:20] == title_match.lower()[:20]:
                    ai.task_id = real_task_id
                    break
        await _log(db, "execution",
            f"Task card: {task_data.get('title','')}",
            f"Google Tasks card created. ID: {task_data.get('task_id','N/A')}.",
            mid, task_data)

    if not e_tools.get("create_task_card"):
        await _log(db, "execution", "Execution complete", e_text[:300], mid)

    # ── Final orchestrator summary ────────────────────────────────────────────
    summary = (
        f"Pipeline complete. {len(action_items_saved)} action items | "
        f"{events_created} calendar events | {tasks_created} task cards | "
        f"Overloaded: {overloaded_owners or 'none'}"
    )
    await _log(db, "orchestrator", "Meeting processing complete", summary, mid, {
        "action_items_created": len(action_items_saved),
        "events_created": events_created,
        "tasks_created": tasks_created,
        "overloaded_owners": overloaded_owners,
    })

    meeting.status = "processed"
    meeting.processed_at = datetime.now(timezone.utc)

    # Send Slack notification
    try:
        from tools.slack_tool import send_pipeline_summary
        # Get latest cognitive states
        from sqlalchemy import select as sa_slack
        cog_result = await db.execute(
            sa_slack(CognitiveState)
            .where(CognitiveState.user_id == settings.user_id)
            .order_by(CognitiveState.calculated_at.desc())
            .limit(50)
        )
        all_cog = cog_result.scalars().all()
        seen = set()
        latest_cog = []
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

    return {
        "meeting_id": str(mid),
        "action_items_created": len(action_items_saved),
        "events_created": events_created,
        "tasks_created": tasks_created,
        "overloaded_owners": overloaded_owners,
    }


async def run_task_pipeline(db: AsyncSession, action_item: ActionItem) -> dict:
    """Flow B: single manual task — cognitive + schedule."""
    run_id = uuid.uuid4().hex[:6]

    existing = await db.execute(
        select(ActionItem).where(
            ActionItem.user_id == settings.user_id,
            ActionItem.owner == action_item.owner,
            ActionItem.status.in_(["pending", "scheduled"]),
        )
    )
    tasks = [
        {"title": t.title, "duration_minutes": t.duration_minutes,
         "complexity": t.complexity, "priority": t.priority,
         "deadline": t.deadline.isoformat() if t.deadline else None}
        for t in existing.scalars().all()
    ]

    cog_prompt = (
        f"Calculate cognitive load for {action_item.owner}.\n"
        f"Their current tasks:\n{json.dumps(tasks, indent=2)}"
    )
    # Use a fresh agent without template variables for direct calls
    from google.adk.agents import LlmAgent
    from agents.adk_agents import MODEL
    from agents.adk_tools import calculate_cognitive_load_tool
    direct_cog_agent = LlmAgent(
        name=f"cognitive_direct_{run_id}",
        model=MODEL,
        description="Calculate cognitive load directly.",
        instruction=cog_prompt,
        tools=[calculate_cognitive_load_tool],
        output_key="cognitive_result",
    )
    c_events, c_text = await _run_agent(direct_cog_agent, f"task_cog_{run_id}", cog_prompt)
    c_tools = _extract_tool_results(c_events)

    cog_data = None
    for data in c_tools.get("calculate_cognitive_load", []):
        if data.get("owner") == action_item.owner:
            cog_data = data
            break

    if cog_data:
        db.add(CognitiveState(
            user_id=settings.user_id,
            owner=action_item.owner,
            load_score=cog_data.get("load_score", 0),
            capacity=cog_data.get("capacity", 480),
            overload_flag=cog_data.get("overload_flag", False),
            context_switches=cog_data.get("context_switches", 0),
        ))
        await _log(db, "cognitive",
            f"{action_item.owner} at {cog_data.get('load_percentage', 0)}%",
            cog_data.get("recommendation", c_text[:300]),
            metadata=cog_data)
        await db.flush()

    return {
        "cognitive_state": cog_data or {},
        "overloaded": cog_data.get("overload_flag", False) if cog_data else False,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────
def _extract_action_items(text: str) -> list:
    for pattern in [r'"action_items"\s*:\s*(\[.*?\])', r'\[\s*\{[^}]*"title"[^}]*"owner"[^}]*\}.*?\]']:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                group = m.group(1) if '"action_items"' in pattern else m.group(0)
                items = json.loads(group)
                if isinstance(items, list) and items:
                    return items
            except (json.JSONDecodeError, IndexError):
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

async def recalculate_load_for_owner(db: AsyncSession, owner: str) -> dict:
    """
    Instantly recalculates cognitive load for an owner using pure Python.
    No ADK agent, no Vertex AI — uses the same Sweller's CLT formula.
    Called when task status changes or Recalculate button is clicked.
    """
    from datetime import datetime, timezone
    from db.models import CognitiveState

    # Get all pending/scheduled tasks for this owner
    result = await db.execute(
        select(ActionItem).where(
            ActionItem.user_id == settings.user_id,
            ActionItem.owner == owner,
            ActionItem.status.in_(["pending", "scheduled"]),
        )
    )
    tasks = result.scalars().all()

    capacity = 480.0
    overload_threshold = settings.overload_threshold

    if not tasks:
        cog = CognitiveState(
            user_id=settings.user_id,
            owner=owner,
            load_score=0.0,
            capacity=capacity,
            overload_flag=False,
            context_switches=0,
        )
        db.add(cog)
        await db.flush()
        return {"owner": owner, "load_percentage": 0.0, "overload_flag": False}

    # Domain detection for context switches
    DOMAINS = {
        "code":     ["api","backend","frontend","bug","deploy","code","build","test","review","implement","debug"],
        "writing":  ["doc","report","deck","slide","write","draft","proposal","email","document","blog"],
        "meetings": ["sync","meeting","call","interview","1:1","standup","demo","presentation","discuss"],
        "admin":    ["invoice","bill","admin","finance","hr","contract","expense","approval"],
    }

    def get_domain(title: str) -> str:
        tl = title.lower()
        for d, kws in DOMAINS.items():
            if any(k in tl for k in kws):
                return d
        return "other"

    def get_urgency(deadline, priority: int) -> float:
        now = datetime.now(timezone.utc)
        dl_urgency = 0.5
        if deadline:
            try:
                dl = deadline if hasattr(deadline, 'tzinfo') else datetime.fromisoformat(str(deadline))
                if dl.tzinfo is None:
                    dl = dl.replace(tzinfo=timezone.utc)
                days = (dl - now).days
                if days <= 0:    dl_urgency = 1.0
                elif days <= 1:  dl_urgency = 0.95
                elif days <= 3:  dl_urgency = 0.75
                elif days <= 7:  dl_urgency = 0.55
                else:            dl_urgency = 0.35
            except Exception:
                pass
        return round(0.6 * dl_urgency + 0.4 * (priority / 5.0), 3)

    # Context switches
    switches = 0
    if len(tasks) > 1:
        prev = get_domain(tasks[0].title)
        for t in tasks[1:]:
            cur = get_domain(t.title)
            if cur != prev:
                switches += 1
            prev = cur

    # Calculate load
    total_load = 0.0
    for t in tasks:
        dur = float(t.duration_minutes or 60)
        cplx = max(1, min(5, int(t.complexity or 3)))
        pri = max(1, min(5, int(t.priority or 3)))
        cw = cplx / 5.0
        uf = get_urgency(t.deadline, pri)
        total_load += dur * cw * uf

    total_load += switches * 15
    pct = round((total_load / capacity) * 100, 1)
    overload = total_load > capacity * overload_threshold

    # Save to DB
    cog = CognitiveState(
        user_id=settings.user_id,
        owner=owner,
        load_score=round(total_load, 1),
        capacity=capacity,
        overload_flag=overload,
        context_switches=switches,
    )
    db.add(cog)
    await db.flush()
    logger.info(f"[FastRecalc] {owner}: {pct}% overload={overload}")
    return {"owner": owner, "load_percentage": pct, "overload_flag": overload}


async def recalculate_all_owners(db: AsyncSession) -> list:
    """Recalculate cognitive load for all owners with pending tasks instantly."""
    result = await db.execute(
        select(ActionItem.owner).where(
            ActionItem.user_id == settings.user_id,
            ActionItem.status.in_(["pending", "scheduled"]),
        ).distinct()
    )
    owners = result.scalars().all()
    results = []
    for owner in owners:
        r = await recalculate_load_for_owner(db, owner)
        results.append(r)
    return results
