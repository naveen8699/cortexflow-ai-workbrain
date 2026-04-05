"""
WorkBrain ADK Runner
Bridge between FastAPI and the ADK multi-agent graph.
Runs agent pipelines and persists results to Cloud SQL by parsing ADK event stream.
"""
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk import types as adk_types
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from agents.adk_agents import root_agent
from config import settings
from db.models import ActionItem, CognitiveState, DecisionLog, Meeting

logger = logging.getLogger(__name__)

# Shared instances — initialised once at app startup
_session_service = InMemorySessionService()
_runner = Runner(
    agent=root_agent,
    app_name="workbrain",
    session_service=_session_service,
)


# ── Helper: write decision log entry ─────────────────────────────────────────
async def _log_decision(
    db: AsyncSession,
    agent: str,
    decision: str,
    reason: str,
    meeting_id: Optional[uuid.UUID] = None,
    metadata: Optional[dict] = None,
) -> DecisionLog:
    entry = DecisionLog(
        user_id=settings.user_id,
        meeting_id=meeting_id,
        agent=agent,
        decision=decision,
        reason=reason,
        metadata=metadata,
    )
    db.add(entry)
    await db.flush()
    logger.info(f"[{agent}] {decision}")
    return entry


# ── Meeting Pipeline ──────────────────────────────────────────────────────────
async def run_meeting_pipeline(db: AsyncSession, meeting: Meeting) -> dict:
    """
    Full 4-agent ADK pipeline for meeting transcript processing.
    Flow: orchestrator → transcript_agent → cognitive_agent → scheduler_agent → execution_agent
    All results written to Cloud SQL via event stream parsing.
    """
    session_id = f"mtg_{meeting.id}_{uuid.uuid4().hex[:6]}"
    user_id = settings.user_id
    meeting_id = meeting.id

    logger.info(f"ADK pipeline START | session={session_id}")

    # Create fresh ADK session for this pipeline run
    await _session_service.create_session(
        app_name="workbrain",
        user_id=user_id,
        session_id=session_id,
    )

    prompt = (
        f"Process this meeting transcript through all 4 agents in sequence.\n\n"
        f"=== TRANSCRIPT ===\n{meeting.transcript}\n=== END TRANSCRIPT ===\n\n"
        f"Pipeline: transcript_agent → cognitive_agent → scheduler_agent → execution_agent.\n"
        f"Follow every step completely before moving to the next."
    )

    # Execute ADK pipeline — collects all events
    all_events: list = []
    final_response = ""

    async for event in _runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=adk_types.Content(
            role="user",
            parts=[adk_types.Part(text=prompt)],
        ),
    ):
        all_events.append(event)
        # Capture agent activity for logging
        author = getattr(event, "author", "")
        if author and hasattr(event, "content") and event.content:
            for part in (event.content.parts or []):
                txt = getattr(part, "text", "")
                if txt:
                    logger.debug(f"  [{author}] {txt[:150]}")

        # Capture final response text
        if hasattr(event, "is_final_response") and event.is_final_response():
            if event.content and event.content.parts:
                final_response = " ".join(
                    p.text for p in event.content.parts if getattr(p, "text", "")
                )

    logger.info(f"ADK pipeline received {len(all_events)} events")

    # Parse events → persist to Cloud SQL
    return await _persist_pipeline_results(db, meeting, all_events, final_response)


async def _persist_pipeline_results(
    db: AsyncSession,
    meeting: Meeting,
    events: list,
    final_response: str,
) -> dict:
    """
    Walks ADK events, extracts tool call results and agent text,
    writes structured data to all 4 Cloud SQL tables.
    """
    meeting_id = meeting.id
    user_id = settings.user_id

    action_items_saved: list[ActionItem] = []
    events_created = 0
    tasks_created = 0
    overloaded_owners: list[str] = []
    cognitive_owners_written: set[str] = set()
    transcript_parsed = False

    for event in events:
        if not (hasattr(event, "content") and event.content and event.content.parts):
            continue

        author = getattr(event, "author", "unknown")

        for part in event.content.parts:
            # ── Tool result → DB write ────────────────────────────────────
            fn_resp = getattr(part, "function_response", None)
            if fn_resp:
                fn_name  = getattr(fn_resp, "name", "")
                raw_resp = getattr(fn_resp, "response", {})
                data = raw_resp if isinstance(raw_resp, dict) else _safe_json(str(raw_resp))

                if not data or "error" in data:
                    continue

                # calculate_cognitive_load result → cognitive_state + decisions_log
                if fn_name == "calculate_cognitive_load":
                    owner = data.get("owner", "unknown")
                    if owner not in cognitive_owners_written:
                        cognitive_owners_written.add(owner)
                        cog = CognitiveState(
                            user_id=user_id,
                            owner=owner,
                            load_score=data.get("load_score", 0.0),
                            capacity=data.get("capacity", 480.0),
                            overload_flag=data.get("overload_flag", False),
                            context_switches=data.get("context_switches", 0),
                        )
                        db.add(cog)
                        await db.flush()

                        if data.get("overload_flag"):
                            overloaded_owners.append(owner)

                        await _log_decision(
                            db, "cognitive",
                            f"{owner} at {data.get('load_percentage', 0)}% capacity",
                            data.get("recommendation", ""),
                            meeting_id,
                            {
                                "owner": owner,
                                "load_percentage": data.get("load_percentage"),
                                "overload_flag": data.get("overload_flag"),
                                "context_switches": data.get("context_switches"),
                                "task_breakdown": data.get("task_breakdown", []),
                            },
                        )

                # create_calendar_event result → decisions_log
                elif fn_name == "create_calendar_event":
                    events_created += 1
                    title = data.get("title", "")
                    await _log_decision(
                        db, "scheduler",
                        f"Calendar event created: {title}",
                        (
                            f"Calendar event '{title}' scheduled from {data.get('start','')} "
                            f"to {data.get('end','')}. "
                            f"Owner had available capacity and required focus time."
                        ),
                        meeting_id,
                        data,
                    )

                # create_task_card result → decisions_log
                elif fn_name == "create_task_card":
                    tasks_created += 1
                    title = data.get("title", "")
                    await _log_decision(
                        db, "execution",
                        f"Task card created: {title}",
                        f"Google Tasks card created for '{title}'. Task ID: {data.get('task_id', 'N/A')}.",
                        meeting_id,
                        data,
                    )

            # ── Agent text response → extract action items ────────────────
            text = getattr(part, "text", "")
            if not text:
                continue

            # Parse action items from transcript_agent response (only once)
            if author == "transcript_agent" and not transcript_parsed:
                items = _extract_action_items_from_text(text)
                if items:
                    transcript_parsed = True
                    for item in items:
                        dl = _parse_iso(item.get("deadline"))
                        ai = ActionItem(
                            user_id=user_id,
                            meeting_id=meeting_id,
                            title=item.get("title", "Untitled"),
                            owner=item.get("owner", user_id),
                            deadline=dl,
                            priority=max(1, min(5, int(item.get("priority", 3)))),
                            complexity=max(1, min(5, int(item.get("complexity", 3)))),
                            duration_minutes=int(item.get("duration_minutes", 60)),
                            status="pending",
                        )
                        db.add(ai)
                        action_items_saved.append(ai)

                    await db.flush()
                    await _log_decision(
                        db, "transcript",
                        f"Extracted {len(action_items_saved)} action items",
                        (
                            f"Gemini analysed the transcript and identified "
                            f"{len(action_items_saved)} action items across "
                            f"{len(set(a.owner for a in action_items_saved))} owners."
                        ),
                        meeting_id,
                        {"action_item_count": len(action_items_saved)},
                    )

                # Extract meeting title + summary
                title_m = re.search(r'"meeting_title"\s*:\s*"([^"]{1,80})"', text)
                if title_m and not meeting.title:
                    meeting.title = title_m.group(1)

                summary_m = re.search(r'"summary"\s*:\s*"([^"]{1,500})"', text)
                if summary_m:
                    meeting.summary = summary_m.group(1)

    # Log overload skips from scheduler
    for owner in overloaded_owners:
        await _log_decision(
            db, "scheduler",
            f"Skipped calendar blocks for {owner}",
            (
                f"{owner} is overloaded. No calendar blocks added to avoid "
                f"increasing schedule pressure. Task card was still created for tracking. "
                f"Recommend discussing with team which task can be moved."
            ),
            meeting_id,
        )

    # Final orchestrator summary decision
    if final_response:
        summary_text = final_response[:600] if len(final_response) > 600 else final_response
        await _log_decision(
            db, "orchestrator",
            "Meeting processing complete",
            summary_text,
            meeting_id,
            {
                "action_items_created": len(action_items_saved),
                "events_created": events_created,
                "tasks_created": tasks_created,
                "overloaded_owners": overloaded_owners,
            },
        )

    # Finalise meeting row
    meeting.status = "processed"
    meeting.processed_at = datetime.now(timezone.utc)
    await db.flush()

    logger.info(
        f"Pipeline COMPLETE: {len(action_items_saved)} items | "
        f"{events_created} cal events | {tasks_created} tasks | "
        f"overloaded: {overloaded_owners}"
    )

    return {
        "meeting_id": str(meeting_id),
        "action_items_created": len(action_items_saved),
        "events_created": events_created,
        "tasks_created": tasks_created,
        "overloaded_owners": overloaded_owners,
    }


# ── Manual Task Pipeline ──────────────────────────────────────────────────────
async def run_task_pipeline(db: AsyncSession, action_item: ActionItem) -> dict:
    """
    Flow B: single manual task entry.
    Runs cognitive_agent → scheduler_agent (if capacity) → execution_agent.
    """
    session_id = f"task_{action_item.id}_{uuid.uuid4().hex[:6]}"

    # Get existing tasks for this owner
    result = await db.execute(
        select(ActionItem).where(
            ActionItem.user_id == settings.user_id,
            ActionItem.owner == action_item.owner,
            ActionItem.status.in_(["pending", "scheduled"]),
        )
    )
    all_tasks = [
        {
            "title": t.title,
            "duration_minutes": t.duration_minutes,
            "complexity": t.complexity,
            "priority": t.priority,
            "deadline": t.deadline.isoformat() if t.deadline else None,
        }
        for t in result.scalars().all()
    ]

    await _session_service.create_session(
        app_name="workbrain",
        user_id=settings.user_id,
        session_id=session_id,
    )

    prompt = (
        f"A new task was manually added:\n"
        f"Title: {action_item.title}\n"
        f"Owner: {action_item.owner}\n"
        f"Duration: {action_item.duration_minutes} minutes\n"
        f"Priority: {action_item.priority}/5\n"
        f"Complexity: {action_item.complexity}/5\n"
        f"Deadline: {action_item.deadline.isoformat() if action_item.deadline else 'none'}\n\n"
        f"Current tasks for {action_item.owner}:\n{json.dumps(all_tasks, indent=2)}\n\n"
        f"Run cognitive_agent to recalculate load, then scheduler_agent if not overloaded, "
        f"then execution_agent to create task card and produce decisions."
    )

    all_events: list = []
    final_response = ""

    async for event in _runner.run_async(
        user_id=settings.user_id,
        session_id=session_id,
        new_message=adk_types.Content(role="user", parts=[adk_types.Part(text=prompt)]),
    ):
        all_events.append(event)
        if hasattr(event, "is_final_response") and event.is_final_response():
            if event.content and event.content.parts:
                final_response = " ".join(p.text for p in event.content.parts if getattr(p, "text", ""))

    # Extract cognitive result and persist
    cog_data: Optional[dict] = None
    for event in all_events:
        if not (getattr(event, "content", None) and event.content.parts):
            continue
        for part in event.content.parts:
            fn_resp = getattr(part, "function_response", None)
            if fn_resp and getattr(fn_resp, "name", "") == "calculate_cognitive_load":
                raw = getattr(fn_resp, "response", {})
                cog_data = raw if isinstance(raw, dict) else _safe_json(str(raw))
                if cog_data:
                    db.add(CognitiveState(
                        user_id=settings.user_id,
                        owner=action_item.owner,
                        load_score=cog_data.get("load_score", 0),
                        capacity=cog_data.get("capacity", 480),
                        overload_flag=cog_data.get("overload_flag", False),
                        context_switches=cog_data.get("context_switches", 0),
                    ))
                    await _log_decision(
                        db, "cognitive",
                        f"{action_item.owner} at {cog_data.get('load_percentage', 0)}% after new task",
                        cog_data.get("recommendation", final_response[:300]),
                        metadata=cog_data,
                    )
                    await db.flush()
                    break

    return {
        "cognitive_state": cog_data or {},
        "overloaded": cog_data.get("overload_flag", False) if cog_data else False,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────
def _extract_action_items_from_text(text: str) -> list[dict]:
    """Extract action_items array from agent text response."""
    # Try to find action_items key in JSON
    for pattern in [
        r'"action_items"\s*:\s*(\[.*?\])',
        r'\[\s*\{[^}]*"title"[^}]*"owner"[^}]*\}.*?\]',
    ]:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                group = m.group(1) if '"action_items"' in pattern else m.group(0)
                items = json.loads(group)
                if isinstance(items, list) and items:
                    return items
            except (json.JSONDecodeError, IndexError):
                pass

    # Try to parse the whole text as JSON
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "action_items" in obj:
            return obj["action_items"]
    except (json.JSONDecodeError, TypeError):
        pass

    return []


def _safe_json(val: str) -> dict:
    try:
        result = json.loads(val)
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None
