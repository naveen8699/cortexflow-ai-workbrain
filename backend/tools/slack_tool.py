"""
WorkBrain Slack Notifier
Sends meeting pipeline results to Slack after processing.
"""
import logging
from typing import Optional
logger = logging.getLogger(__name__)

def send_pipeline_summary(
    meeting_title: str,
    action_items: list,
    cognitive_states: list,
    overloaded_owners: list,
    events_created: int,
    tasks_created: int,
) -> bool:
    """Send a WorkBrain pipeline summary to Slack."""
    try:
        import os
        from slack_sdk import WebClient

        token = os.environ.get("SLACK_BOT_TOKEN")
        channel = os.environ.get("SLACK_CHANNEL_ID")

        if not token or not channel:
            logger.warning("Slack not configured — skipping notification")
            return False

        client = WebClient(token=token)

        # Build per-owner task summary
        owners_summary = {}
        for item in action_items:
            owner = item.owner
            if owner not in owners_summary:
                owners_summary[owner] = []
            deadline = item.deadline.strftime("%b %d") if item.deadline else "No deadline"
            priority_labels = {1: "Low", 2: "Low", 3: "Medium", 4: "High", 5: "Critical"}
            owners_summary[owner].append(
                f"• {item.title} — {deadline} ({priority_labels.get(item.priority, 'Medium')})"
            )

        # Build cognitive load summary
        load_lines = []
        for cs in cognitive_states:
            if cs.overload_flag:
                load_lines.append(f"🔴 *{cs.owner}*: {cs.load_percentage:.0f}% — OVERLOADED")
            elif cs.load_percentage >= 70:
                load_lines.append(f"🟡 *{cs.owner}*: {cs.load_percentage:.0f}% — High")
            else:
                load_lines.append(f"🟢 *{cs.owner}*: {cs.load_percentage:.0f}% — Healthy")

        # Build blocks
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🧠 WorkBrain — {meeting_title}",
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Action Items:*\n{tasks_created} tasks created"},
                    {"type": "mrkdwn", "text": f"*Calendar Events:*\n{events_created} blocks scheduled"},
                ]
            },
            {"type": "divider"},
        ]

        # Add per-owner sections
        for owner, items in owners_summary.items():
            cs = next((c for c in cognitive_states if c.owner == owner), None)
            if cs and cs.overload_flag:
                owner_header = f"⚠️ *{owner}* — OVERLOADED ({cs.load_percentage:.0f}%)"
                owner_note = "_No calendar blocks added to protect schedule_"
            elif cs:
                owner_header = f"✅ *{owner}* — {cs.load_percentage:.0f}% capacity"
                owner_note = ""
            else:
                owner_header = f"✅ *{owner}*"
                owner_note = ""

            task_text = "\n".join(items[:5])  # Max 5 tasks per owner
            if len(items) > 5:
                task_text += f"\n_...and {len(items)-5} more_"

            block_text = f"{owner_header}\n{task_text}"
            if owner_note:
                block_text += f"\n{owner_note}"

            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": block_text}
            })

        blocks.append({"type": "divider"})

        # Cognitive load summary
        if load_lines:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Cognitive Load Summary:*\n" + "\n".join(load_lines)
                }
            })

        # Footer
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Powered by WorkBrain · Google ADK + Vertex AI · <https://workbrain-cortexflow-project.web.app/dashboard|View Dashboard>"
                }
            ]
        })

        client.chat_postMessage(
            channel=channel,
            text=f"WorkBrain processed: {meeting_title} — {tasks_created} tasks, {events_created} calendar events",
            blocks=blocks,
        )
        logger.info(f"Slack notification sent for: {meeting_title}")
        return True

    except Exception as e:
        logger.warning(f"Slack notification failed: {e}")
        return False
