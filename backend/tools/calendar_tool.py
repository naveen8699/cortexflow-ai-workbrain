"""
Google Calendar + Tasks MCP Tool Wrappers
These wrap Google APIs as callable functions for ADK @tool decorators.
OAuth setup: run setup_oauth() once before first use.
"""
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
]


def _get_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if os.path.exists(settings.google_token_path):
        creds = Credentials.from_authorized_user_file(settings.google_token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config(
                {
                    "installed": {
                        "client_id": settings.google_oauth_client_id,
                        "client_secret": settings.google_oauth_client_secret,
                        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob"],
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                },
                SCOPES,
            )
            creds = flow.run_local_server(port=0)
        with open(settings.google_token_path, "w") as f:
            f.write(creds.to_json())
    return creds


def setup_oauth():
    """Run once to set up OAuth. Opens browser for Google sign-in."""
    creds = _get_credentials()
    print(f"OAuth complete. Token saved to {settings.google_token_path}")
    return creds


def create_calendar_event_api(
    title: str, start_time: datetime, end_time: datetime, description: str = ""
) -> dict:
    try:
        from googleapiclient.discovery import build
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)
        service = build("calendar", "v3", credentials=_get_credentials(), cache_discovery=False)
        event = service.events().insert(
            calendarId="primary",
            body={
                "summary": title,
                "description": description,
                "start": {"dateTime": start_time.isoformat(), "timeZone": "UTC"},
                "end": {"dateTime": end_time.isoformat(), "timeZone": "UTC"},
                "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 30}]},
            },
        ).execute()
        return {
            "event_id": event["id"],
            "html_link": event.get("htmlLink"),
            "title": title,
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
            "status": "created",
        }
    except Exception as e:
        logger.warning(f"Calendar API error (using mock): {e}")
        return {
            "event_id": f"mock_{title[:15].replace(' ', '_')}",
            "html_link": None,
            "title": title,
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
            "status": "mock_created",
        }


def get_free_slots_api(date: datetime, duration_minutes: int = 60) -> list[dict]:
    try:
        from googleapiclient.discovery import build
        day_start = date.replace(hour=9, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        day_end = date.replace(hour=18, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        service = build("calendar", "v3", credentials=_get_credentials(), cache_discovery=False)
        fb = service.freebusy().query(body={
            "timeMin": day_start.isoformat(),
            "timeMax": day_end.isoformat(),
            "items": [{"id": "primary"}],
        }).execute()
        busy = [
            (
                datetime.fromisoformat(b["start"].replace("Z", "+00:00")),
                datetime.fromisoformat(b["end"].replace("Z", "+00:00")),
            )
            for b in fb["calendars"]["primary"]["busy"]
        ]
        slots, cur, dur = [], day_start, timedelta(minutes=duration_minutes)
        while cur + dur <= day_end:
            slot_end = cur + dur
            overlap = any(not (slot_end <= bs or cur >= be) for bs, be in busy)
            if not overlap:
                slots.append({"start": cur.isoformat(), "end": slot_end.isoformat(), "is_morning": cur.hour < 12})
            cur += timedelta(minutes=30)
        slots.sort(key=lambda x: (not x["is_morning"], x["start"]))
        return slots[:5]
    except Exception as e:
        logger.warning(f"Free slots error (using default 9am): {e}")
        d9 = date.replace(hour=9, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        return [{"start": d9.isoformat(), "end": (d9 + timedelta(minutes=duration_minutes)).isoformat(), "is_morning": True}]


def create_task_api(title: str, due: Optional[datetime] = None, notes: str = "") -> dict:
    try:
        from googleapiclient.discovery import build
        service = build("tasks", "v1", credentials=_get_credentials(), cache_discovery=False)
        body = {"title": title, "notes": notes, "status": "needsAction"}
        if due:
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            body["due"] = due.strftime("%Y-%m-%dT00:00:00.000Z")
        task = service.tasks().insert(tasklist="@default", body=body).execute()
        return {"task_id": task["id"], "title": title, "status": "created"}
    except Exception as e:
        logger.warning(f"Tasks API error (using mock): {e}")
        return {"task_id": f"mock_{title[:15].replace(' ', '_')}", "title": title, "status": "mock_created"}
