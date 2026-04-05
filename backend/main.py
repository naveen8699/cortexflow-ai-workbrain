"""
WorkBrain - FastAPI Application
REST API + CopilotKit AG-UI streaming endpoint
"""
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import vertexai
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

# CopilotKit integration
from copilotkit.integrations.fastapi import add_fastapi_endpoint
from copilotkit import CopilotKitSDK, LangGraphAgent

from agents.adk_runner import run_meeting_pipeline, run_task_pipeline
from config import settings
from db.database import check_db_connection, get_db
from db.models import ActionItem, CognitiveState, DecisionLog, Meeting
from models.schemas import (
    ActionItemResponse,
    AddTaskRequest,
    AddTaskResponse,
    CognitiveStateResponse,
    DashboardResponse,
    DashboardStats,
    DecisionLogResponse,
    MeetingResponse,
    ProcessMeetingRequest,
    ProcessMeetingResponse,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("WorkBrain API starting...")
    vertexai.init(project=settings.gcp_project_id, location=settings.vertex_ai_location)
    logger.info(f"Vertex AI ready | project={settings.gcp_project_id} | model={settings.vertex_ai_model}")
    logger.info("ADK orchestrator ready | sub-agents: transcript, cognitive, scheduler, execution")
    db_ok = await check_db_connection()
    if db_ok:
        logger.info("Cloud SQL connected")
    else:
        logger.warning("Cloud SQL connection FAILED — check proxy or instance")
    yield
    logger.info("WorkBrain API stopping")


app = FastAPI(
    title="WorkBrain API",
    description="AI-powered meeting-to-execution engine | Google ADK + Vertex AI",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow Firebase Hosting + local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://*.web.app",
        "https://*.firebaseapp.com",
        "https://*.run.app",
        settings.frontend_url,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── CopilotKit AG-UI endpoint ─────────────────────────────────────────────────
# This enables the streaming sidebar in the frontend
try:
    from agents.adk_agents import root_agent as workbrain_agent

    sdk = CopilotKitSDK(
        agents=[
            LangGraphAgent(
                name="workbrain",
                description="WorkBrain AI — processes meetings and manages cognitive load",
                agent=workbrain_agent,
            )
        ]
    )
    add_fastapi_endpoint(app, sdk, "/api/copilotkit")
    logger.info("CopilotKit AG-UI endpoint registered at /api/copilotkit")
except Exception as e:
    logger.warning(f"CopilotKit setup skipped: {e}")


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    db_ok = await check_db_connection()
    return {
        "status": "healthy" if db_ok else "degraded",
        "db": "connected" if db_ok else "disconnected",
        "adk": "ready",
        "orchestrator": "workbrain_orchestrator",
        "sub_agents": ["transcript_agent", "cognitive_agent", "scheduler_agent", "execution_agent"],
        "vertex_ai_model": settings.vertex_ai_model,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── POST /api/meetings/process ────────────────────────────────────────────────
@app.post("/api/meetings/process", response_model=ProcessMeetingResponse, status_code=201)
async def process_meeting(request: ProcessMeetingRequest, db: AsyncSession = Depends(get_db)):
    """
    Main demo endpoint.
    Paste transcript → ADK orchestrator coordinates 4 agents → calendar events + tasks created.
    """
    logger.info(f"Processing transcript | len={len(request.transcript)}")

    meeting = Meeting(
        user_id=settings.user_id,
        title=request.title,
        transcript=request.transcript,
        status="processing",
    )
    db.add(meeting)
    await db.flush()

    try:
        result = await run_meeting_pipeline(db, meeting)
    except Exception as e:
        meeting.status = "failed"
        await db.flush()
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")

    decisions_result = await db.execute(
        select(DecisionLog)
        .where(DecisionLog.meeting_id == meeting.id)
        .order_by(DecisionLog.timestamp)
    )
    decisions = decisions_result.scalars().all()

    return ProcessMeetingResponse(
        success=True,
        message=f"Processed via ADK. {result['action_items_created']} action items created.",
        meeting_id=meeting.id,
        action_items_created=result["action_items_created"],
        events_created=result["events_created"],
        tasks_created=result["tasks_created"],
        overloaded_owners=result["overloaded_owners"],
        decisions=[DecisionLogResponse.model_validate(d) for d in decisions],
    )


# ── POST /api/tasks ───────────────────────────────────────────────────────────
@app.post("/api/tasks", response_model=AddTaskResponse, status_code=201)
async def add_task(request: AddTaskRequest, db: AsyncSession = Depends(get_db)):
    """Flow B — manual task entry + cognitive load recalculation via ADK."""
    action_item = ActionItem(
        user_id=settings.user_id,
        title=request.title,
        owner=request.owner,
        deadline=request.deadline,
        priority=request.priority,
        complexity=request.complexity,
        duration_minutes=request.duration_minutes,
        status="pending",
    )
    db.add(action_item)
    await db.flush()

    await run_task_pipeline(db, action_item)

    # Fetch latest cognitive state for this owner
    cog_res = await db.execute(
        select(CognitiveState)
        .where(CognitiveState.user_id == settings.user_id, CognitiveState.owner == request.owner)
        .order_by(desc(CognitiveState.calculated_at))
        .limit(1)
    )
    cog = cog_res.scalar_one_or_none()

    # Fetch latest decisions
    dec_res = await db.execute(
        select(DecisionLog)
        .where(DecisionLog.user_id == settings.user_id)
        .order_by(desc(DecisionLog.timestamp))
        .limit(5)
    )

    return AddTaskResponse(
        success=True,
        message=f"Task added. Load recalculated for {request.owner}.",
        action_item=ActionItemResponse.model_validate(action_item),
        cognitive_state=CognitiveStateResponse.model_validate(cog) if cog else None,
        decisions=[DecisionLogResponse.model_validate(d) for d in dec_res.scalars().all()],
    )


# ── GET /api/dashboard ────────────────────────────────────────────────────────
@app.get("/api/dashboard", response_model=DashboardResponse)
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    """All dashboard data in one call. Frontend polls this every 3 seconds."""
    uid = settings.user_id
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # Meetings (last 10)
    mtg_res = await db.execute(
        select(Meeting).where(Meeting.user_id == uid).order_by(desc(Meeting.created_at)).limit(10)
    )
    meetings = mtg_res.scalars().all()

    # Meetings today count
    cnt_res = await db.execute(
        select(func.count(Meeting.id)).where(Meeting.user_id == uid, Meeting.created_at >= today_start)
    )
    meetings_today = cnt_res.scalar() or 0

    # Action items (last 20)
    ai_res = await db.execute(
        select(ActionItem).where(ActionItem.user_id == uid).order_by(desc(ActionItem.created_at)).limit(20)
    )
    action_items = ai_res.scalars().all()

    # Latest cognitive state per owner (deduplicated)
    cog_res = await db.execute(
        select(CognitiveState).where(CognitiveState.user_id == uid)
        .order_by(desc(CognitiveState.calculated_at)).limit(20)
    )
    seen_owners: set[str] = set()
    cognitive_states: list[CognitiveState] = []
    for cs in cog_res.scalars().all():
        if cs.owner not in seen_owners:
            seen_owners.add(cs.owner)
            cognitive_states.append(cs)

    overloaded = [cs.owner for cs in cognitive_states if cs.overload_flag]
    user_load = next(
        (cs.load_percentage for cs in cognitive_states if cs.owner in (uid, "demo_user")),
        0.0,
    )

    # Decisions (last 15)
    dec_res = await db.execute(
        select(DecisionLog).where(DecisionLog.user_id == uid)
        .order_by(desc(DecisionLog.timestamp)).limit(15)
    )
    decisions = dec_res.scalars().all()

    # Build meeting responses with counts
    meeting_responses = []
    for m in meetings:
        meeting_responses.append(MeetingResponse(
            id=m.id, user_id=m.user_id, title=m.title, status=m.status,
            summary=m.summary, processed_at=m.processed_at, created_at=m.created_at,
            action_items_count=sum(1 for ai in action_items if ai.meeting_id == m.id),
            decisions_count=sum(1 for d in decisions if d.meeting_id == m.id),
        ))

    return DashboardResponse(
        meetings=meeting_responses,
        action_items=[ActionItemResponse.model_validate(ai) for ai in action_items],
        cognitive_states=[CognitiveStateResponse.model_validate(cs) for cs in cognitive_states],
        decisions=[DecisionLogResponse.model_validate(d) for d in decisions],
        stats=DashboardStats(
            meetings_today=meetings_today,
            total_action_items=len(action_items),
            user_load_percentage=user_load,
            total_decisions=len(decisions),
            overloaded_owners=overloaded,
        ),
    )


# ── GET /api/meetings ─────────────────────────────────────────────────────────
@app.get("/api/meetings", response_model=list[MeetingResponse])
async def list_meetings(db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(Meeting).where(Meeting.user_id == settings.user_id)
        .order_by(desc(Meeting.created_at)).limit(20)
    )
    return [MeetingResponse.model_validate(m) for m in res.scalars().all()]


# ── GET /api/meetings/{id}/decisions ─────────────────────────────────────────
@app.get("/api/meetings/{meeting_id}/decisions", response_model=list[DecisionLogResponse])
async def get_meeting_decisions(meeting_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(DecisionLog).where(
            DecisionLog.user_id == settings.user_id,
            DecisionLog.meeting_id == meeting_id,
        ).order_by(DecisionLog.timestamp)
    )
    decisions = res.scalars().all()
    if not decisions:
        raise HTTPException(status_code=404, detail=f"No decisions found for meeting {meeting_id}")
    return [DecisionLogResponse.model_validate(d) for d in decisions]


# ── GET /api/decisions ────────────────────────────────────────────────────────
@app.get("/api/decisions", response_model=list[DecisionLogResponse])
async def list_decisions(limit: int = 30, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(DecisionLog).where(DecisionLog.user_id == settings.user_id)
        .order_by(desc(DecisionLog.timestamp)).limit(limit)
    )
    return [DecisionLogResponse.model_validate(d) for d in res.scalars().all()]


# ── GET /api/tasks ────────────────────────────────────────────────────────────
@app.get("/api/tasks", response_model=list[ActionItemResponse])
async def list_tasks(db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(ActionItem).where(ActionItem.user_id == settings.user_id)
        .order_by(desc(ActionItem.created_at)).limit(50)
    )
    return [ActionItemResponse.model_validate(ai) for ai in res.scalars().all()]
