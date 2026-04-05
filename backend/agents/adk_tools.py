"""
WorkBrain ADK Tools
All functions decorated with @tool are callable by Gemini agents mid-reasoning.
ADK auto-generates JSON schema from Python type hints.
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from google.adk.tools import tool

from config import settings

logger = logging.getLogger(__name__)


@tool
def get_today_iso() -> str:
    """
    Returns today's date and useful relative dates in ISO 8601 format.
    Always call this first when transcript mentions 'today', 'this week', 'by Friday', 'end of day'.

    Returns:
        JSON string with today, tomorrow, this_friday, next_week dates
    """
    now = datetime.now(timezone.utc)
    days_to_fri = (4 - now.weekday()) % 7
    friday = now + timedelta(days=days_to_fri if days_to_fri > 0 else 7)
    return json.dumps({
        "today": now.strftime("%Y-%m-%d"),
        "today_iso": now.isoformat(),
        "tomorrow": (now + timedelta(days=1)).strftime("%Y-%m-%d"),
        "this_friday": friday.strftime("%Y-%m-%d"),
        "next_week": (now + timedelta(days=7)).strftime("%Y-%m-%d"),
    })


@tool
def calculate_cognitive_load(
    owner: str,
    tasks_json: str,
    capacity_minutes: float = 480.0,
) -> str:
    """
    Calculates cognitive load for a person based on Sweller's Cognitive Load Theory (1988).
    Formula: Load = SUM(duration_min * complexity_weight * urgency_factor) + (context_switches * 15)
    Daily capacity = 480 minutes (8-hour workday). Overload threshold = 85%.

    Args:
        owner: Person's name to calculate load for
        tasks_json: JSON array of tasks. Each task must have:
                    title (str), duration_minutes (int), complexity (1-5 int),
                    priority (1-5 int), deadline (ISO string or null)
        capacity_minutes: Daily working minutes, default 480

    Returns:
        JSON string containing: owner, load_score, capacity, overload_flag,
        load_percentage, context_switches, recommendation, task_breakdown
    """
    try:
        tasks = json.loads(tasks_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid tasks_json — must be a valid JSON array"})

    if not tasks:
        return json.dumps({
            "owner": owner, "load_score": 0.0, "capacity": capacity_minutes,
            "overload_flag": False, "load_percentage": 0.0,
            "context_switches": 0,
            "recommendation": f"{owner} has no tasks. Schedule is completely clear.",
        })

    DOMAINS = {
        "code":     ["api", "backend", "frontend", "bug", "deploy", "code", "build", "test", "review", "implement", "debug"],
        "writing":  ["doc", "report", "deck", "slide", "write", "draft", "proposal", "email", "document", "blog"],
        "meetings": ["sync", "meeting", "call", "interview", "1:1", "standup", "demo", "presentation", "discuss"],
        "admin":    ["invoice", "bill", "admin", "finance", "hr", "contract", "expense", "approval"],
    }

    def get_domain(title: str) -> str:
        tl = title.lower()
        for d, kws in DOMAINS.items():
            if any(k in tl for k in kws):
                return d
        return "other"

    def get_urgency(deadline_str: Optional[str], priority: int) -> float:
        now = datetime.now(timezone.utc)
        dl_urgency = 0.5
        if deadline_str:
            try:
                dl = datetime.fromisoformat(str(deadline_str).replace("Z", "+00:00"))
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

    # Count context switches (domain changes in task sequence)
    switches = 0
    if len(tasks) > 1:
        prev = get_domain(tasks[0].get("title", ""))
        for t in tasks[1:]:
            cur = get_domain(t.get("title", ""))
            if cur != prev:
                switches += 1
            prev = cur

    total_load, breakdown = 0.0, []
    for t in tasks:
        dur  = float(t.get("duration_minutes", 60))
        cplx = max(1, min(5, int(t.get("complexity", 3))))
        pri  = max(1, min(5, int(t.get("priority", 3))))
        cw   = cplx / 5.0
        uf   = get_urgency(t.get("deadline"), pri)
        tl   = dur * cw * uf
        total_load += tl
        breakdown.append({
            "title": t.get("title", ""),
            "task_load": round(tl, 1),
            "complexity_weight": round(cw, 2),
            "urgency_factor": round(uf, 2),
        })

    total_load += switches * 15  # 15-min penalty per context switch
    pct     = round((total_load / capacity_minutes) * 100, 1)
    overload = total_load > capacity_minutes * settings.overload_threshold

    if pct >= 130:
        rec = (f"{owner} is critically overloaded at {pct}% with {len(tasks)} tasks "
               f"and {switches} context switches. Drop or reschedule the lowest-priority task immediately.")
    elif overload:
        rec = (f"{owner} is overloaded at {pct}%. No new calendar blocks added. "
               f"Recommend moving the lowest-priority task with a flexible deadline to tomorrow.")
    elif pct >= 70:
        rec = f"{owner} is at {pct}% capacity — manageable."
        if switches >= 3:
            rec += f" {switches} context switches detected. Batching similar tasks would help."
    else:
        rec = f"{owner} has available capacity at {pct}%. Can safely take on more work."

    logger.info(f"[CognitiveLoad] {owner}: {pct}% overload={overload} switches={switches}")

    return json.dumps({
        "owner": owner,
        "load_score": round(total_load, 1),
        "capacity": capacity_minutes,
        "overload_flag": overload,
        "load_percentage": pct,
        "context_switches": switches,
        "recommendation": rec,
        "task_breakdown": breakdown,
    })


@tool
def get_calendar_free_slots(date_iso: str, duration_minutes: int = 60) -> str:
    """
    Finds available time slots on a given day for scheduling focus blocks or meetings.
    Returns morning slots first (optimal for cognitively demanding tasks).

    Args:
        date_iso: Date to check in ISO 8601 format e.g. '2024-04-07T00:00:00+00:00'
        duration_minutes: Required slot duration in minutes (e.g. 60, 90, 120)

    Returns:
        JSON string with list of available slots: [{start, end, is_morning}]
    """
    try:
        from tools.calendar_tool import get_free_slots_api
        dt = datetime.fromisoformat(date_iso.replace("Z", "+00:00"))
        slots = get_free_slots_api(dt, duration_minutes)
        return json.dumps({"slots": slots, "date": date_iso, "duration_minutes": duration_minutes})
    except Exception as e:
        logger.warning(f"Free slots error: {e}")
        try:
            dt = datetime.fromisoformat(date_iso.replace("Z", "+00:00"))
        except Exception:
            dt = datetime.now(timezone.utc)
        d9 = dt.replace(hour=9, minute=0, second=0, microsecond=0)
        if d9.tzinfo is None:
            d9 = d9.replace(tzinfo=timezone.utc)
        return json.dumps({"slots": [{"start": d9.isoformat(), "end": (d9 + timedelta(minutes=duration_minutes)).isoformat(), "is_morning": True}]})


@tool
def create_calendar_event(
    title: str,
    start_iso: str,
    end_iso: str,
    description: str = "",
) -> str:
    """
    Creates a Google Calendar event via Calendar MCP.
    Use prefix '🎯 Focus: ' for focus blocks, '⏰ Due: ' for deadline reminders, no prefix for meetings.

    Args:
        title: Clear descriptive event title
        start_iso: Start datetime in ISO 8601 format e.g. '2024-04-07T09:00:00+00:00'
        end_iso: End datetime in ISO 8601 format
        description: Context for the attendee including why this slot was chosen

    Returns:
        JSON string with event_id, html_link, title, start, end, status
    """
    try:
        from tools.calendar_tool import create_calendar_event_api
        start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        end   = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        result = create_calendar_event_api(title, start, end, description)
        logger.info(f"[CalendarMCP] Created: {title}")
        return json.dumps(result)
    except Exception as e:
        logger.warning(f"Calendar event error: {e}")
        return json.dumps({
            "event_id": f"mock_{title[:12].replace(' ','_')}",
            "html_link": None, "title": title,
            "start": start_iso, "end": end_iso, "status": "mock_created",
        })


@tool
def create_task_card(
    title: str,
    owner: str,
    deadline_iso: Optional[str] = None,
    notes: str = "",
) -> str:
    """
    Creates a Google Tasks card via Tasks MCP for an action item.
    Call this for EVERY action item extracted from the meeting transcript.

    Args:
        title: Clear actionable task title
        owner: Name of the person responsible for this task
        deadline_iso: Due date in ISO format or null if no hard deadline
        notes: Additional context: priority level, meeting source, complexity

    Returns:
        JSON string with task_id, title, status
    """
    try:
        from tools.calendar_tool import create_task_api
        dl = None
        if deadline_iso:
            dl = datetime.fromisoformat(str(deadline_iso).replace("Z", "+00:00"))
            if dl.tzinfo is None:
                dl = dl.replace(tzinfo=timezone.utc)
        full_notes = f"Owner: {owner}\n{notes}\nCreated automatically by WorkBrain."
        result = create_task_api(title, dl, full_notes)
        logger.info(f"[TasksMCP] Created task: {title} for {owner}")
        return json.dumps(result)
    except Exception as e:
        logger.warning(f"Task create error: {e}")
        return json.dumps({"task_id": f"mock_{title[:12].replace(' ','_')}", "title": title, "status": "mock_created"})
