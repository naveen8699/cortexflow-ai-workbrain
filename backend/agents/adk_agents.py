"""
WorkBrain ADK Agents — ADK CustomAgent pattern with session state templating.
Each agent reads its input from session.state via {variable} templating.
"""
from google.adk.agents import LlmAgent
from google.adk.agents.context_cache_config import ContextCacheConfig
from tools.slack_mcp import get_slack_mcp_toolset
from google.adk.tools.google_search_tool import GoogleSearchTool
from google.genai import types as genai_types
from pydantic import BaseModel
from typing import List, Optional as Opt

class ActionItemSchema(BaseModel):
    title: str
    owner: str
    deadline: Opt[str] = None
    priority: int = 3
    complexity: int = 3
    duration_minutes: int = 60
    needs_focus_block: bool = False

class OverloadSignal(BaseModel):
    owner: str
    signal: str

class TranscriptOutput(BaseModel):
    meeting_title: str
    action_items: List[ActionItemSchema]
    overload_signals: List[OverloadSignal] = []
    summary: str

google_search = GoogleSearchTool(bypass_multi_tools_limit=True)
from tools.alloydb_mcp import get_alloydb_mcp_toolset
from agents.adk_tools import (
    get_today_iso_tool,
    calculate_cognitive_load_tool,
    get_calendar_free_slots_tool,
    create_calendar_event_tool,
    create_task_card_tool,
)
import os

MODEL = os.environ.get("VERTEX_AI_MODEL", "gemini-2.5-flash")
MODEL_LIGHT = "gemini-1.5-flash"

# ── Agent 1: Transcript Agent ─────────────────────────────────────────────────
transcript_agent = LlmAgent(
    name="transcript_agent",
    model=MODEL,
    generate_content_config=genai_types.GenerateContentConfig(
        response_mime_type="application/json",
    ),
    output_schema=TranscriptOutput,
    description="Extracts structured action items from meeting transcripts.",
    instruction="""You are WorkBrain's Transcript Agent.

MANDATORY FIRST ACTION: Call get_today_iso tool immediately to get today's date.

DATE RULES:
- Use the year from get_today_iso for ALL deadlines
- NEVER use 2024 or any past year
- If a month has already passed this year, use next year

Extract ALL action items from this transcript:
{transcript_prompt}

For each action item return:
{
  "title": "clear actionable task",
  "owner": "person name",
  "deadline": "YYYY-MM-DD or null",
  "priority": 1-5,
  "complexity": 1-5,
  "duration_minutes": 30/60/90/120/180/240/300/360/480,
  "needs_focus_block": true if complexity>=4 OR duration>=120
}

Return ONLY valid JSON:
{
  "meeting_title": "short title",
  "action_items": [...],
  "overload_signals": [{"owner": "...", "signal": "quote"}],
  "summary": "2-3 sentence summary"
}""",
    tools=[get_today_iso_tool],
    output_key="transcript_result",
)

# ── Agent 2: Cognitive Load Agent ─────────────────────────────────────────────
cognitive_agent = LlmAgent(
    name="cognitive_agent",
    model=MODEL_LIGHT,
    description="Calculates cognitive load per owner using AlloyDB MCP for historical context.",
    instruction="""You are WorkBrain's Cognitive Load Agent.

{cognitive_prompt}

For EACH owner listed above:
1. Optionally use get_cognitive_states MCP tool to check historical load
2. Call calculate_cognitive_load with their name and ALL their tasks as JSON array
3. Note overload_flag — if true, NO calendar blocks for this person

Return summary for all owners: load %, overload status, recommendation.""",
    tools=[calculate_cognitive_load_tool, get_alloydb_mcp_toolset()],
    output_key="cognitive_result",
)

# ── Agent 3: Scheduler Agent ──────────────────────────────────────────────────
scheduler_agent = LlmAgent(
    name="scheduler_agent",
    model=MODEL,
    description="Creates Google Calendar events. Skips overloaded owners.",
    instruction="""You are WorkBrain's Scheduler Agent.

{scheduler_prompt}

APAC HOLIDAY CHECK (optional, max ONE search):
Only use google_search if deadline falls on a weekend or you suspect a holiday.
Query: "India public holidays May 2026". Skip search if dates look clear.

CRITICAL: Skip calendar blocks for ALL overloaded owners listed above.

For non-overloaded owners:
- needs_focus_block=true: call get_calendar_free_slots then create_calendar_event with title "🎯 Focus: [task]" and owner="[person name]"
- deadline only: create 30-min reminder at 9am on deadline day with title "⏰ Due: [task]" and owner="[person name]"
- Always pass the owner parameter so the event invitation is sent to their email

Return summary of all events created with their IDs.""",
    tools=[get_calendar_free_slots_tool, create_calendar_event_tool, google_search],
    output_key="scheduler_result",
)

# ── Agent 4: Execution Agent ──────────────────────────────────────────────────
execution_agent = LlmAgent(
    name="execution_agent",
    model=MODEL_LIGHT,
    description="Creates Google Tasks cards, sends Slack MCP notifications, produces decisions log.",
    instruction="""You are WorkBrain's Execution Agent — the FINAL agent.

{execution_prompt}

1. Call create_task_card for EVERY action item including overloaded owners.
   Include in notes: priority, deadline, complexity, source meeting.

2. Produce COMPLETE decisions list:
[{"agent": "...", "decision": "short title", "reason": "plain English with names/numbers/dates"}]

Good reason: "Arjun is overloaded at 138%. No calendar block added. Task card created for tracking."
Bad reason: "Task processed."
Cover ALL decisions: extraction, load calc, scheduling, task creation.""",
    tools=[create_task_card_tool, get_slack_mcp_toolset()],
    output_key="execution_result",
)

# ── WorkBrain Pipeline Agent (CustomAgent) ────────────────────────────────────
from agents.workbrain_pipeline_agent import WorkBrainPipelineAgent

workbrain_pipeline = WorkBrainPipelineAgent(
    name="workbrain_pipeline",
    description="WorkBrain CustomAgent — orchestrates 4-agent pipeline with AlloyDB AI persistence between steps.",
    sub_agents=[
        transcript_agent,
        cognitive_agent,
        scheduler_agent,
        execution_agent,
    ],
)

# root_agent for ADK compatibility
root_agent = workbrain_pipeline