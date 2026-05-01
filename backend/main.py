"""
WorkBrain - FastAPI Application
REST API + CopilotKit AG-UI streaming endpoint
"""
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import vertexai
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.adk_runner import run_meeting_pipeline_custom, run_task_pipeline  # CHANGED
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

import asyncio
from collections import defaultdict
from typing import AsyncGenerator

# Progress queues for SSE streaming (job_id -> asyncio.Queue)
_progress_queues: dict = {}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("WorkBrain API starting...")
    import os
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    os.environ["GOOGLE_CLOUD_PROJECT"] = settings.gcp_project_id
    os.environ["GOOGLE_CLOUD_LOCATION"] = settings.vertex_ai_location
    vertexai.init(project=settings.gcp_project_id, location=settings.vertex_ai_location)
    logger.info(f"Vertex AI configured | project={settings.gcp_project_id} | model={settings.vertex_ai_model}")
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://*.web.app",
        "https://*.firebaseapp.com",
        "https://*.run.app",
        "https://workbrain-frontend-114869691007.us-central1.run.app",
        "https://workbrain-cortexflow-project.web.app",
        "https://workbrain-cortexflow-project.firebaseapp.com",
        "https://*.cloudshell.dev",
        settings.frontend_url,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/copilotkit")
async def copilotkit_endpoint(request: Request):
    import json
    from fastapi.responses import StreamingResponse

    body = await request.json()
    messages = body.get("messages", [])
    last_msg = messages[-1].get("content", "") if messages else ""

    async def stream():
        prefix = "data: "
        suffix = "\n\n"
        yield prefix + json.dumps({"type": "text", "content": "WorkBrain AI is processing..."}) + suffix
        try:
            from agents.adk_agents import root_agent
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService
            from google.adk import types as adk_types
            import uuid

            svc = InMemorySessionService()
            runner = Runner(agent=root_agent, app_name="workbrain", session_service=svc)
            session_id = "copilot_" + uuid.uuid4().hex[:8]
            await svc.create_session(app_name="workbrain", user_id="demo_user", session_id=session_id)

            async for event in runner.run_async(
                user_id="demo_user",
                session_id=session_id,
                new_message=adk_types.Content(role="user", parts=[adk_types.Part(text=last_msg)])
            ):
                if hasattr(event, "is_final_response") and event.is_final_response():
                    if event.content and event.content.parts:
                        text = " ".join(
                            p.text for p in event.content.parts if getattr(p, "text", "")
                        )
                        yield prefix + json.dumps({"type": "text", "content": text}) + suffix
        except Exception as e:
            yield prefix + json.dumps({"type": "text", "content": "Agent error: " + str(e)}) + suffix
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/health")
async def health():
    db_ok = await check_db_connection()
    return {
        "status": "healthy" if db_ok else "degraded",
        "db": "connected" if db_ok else "disconnected",
        "adk": "ready",
        "orchestrator": "workbrain_pipeline",
        "sub_agents": ["transcript_agent", "cognitive_agent", "scheduler_agent", "execution_agent"],
        "vertex_ai_model": settings.vertex_ai_model,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/meetings/stream/{job_id}")
async def stream_pipeline_progress(job_id: str):
    """SSE endpoint streaming real pipeline progress events."""
    import json
    from fastapi.responses import StreamingResponse

    if job_id not in _progress_queues:
        _progress_queues[job_id] = asyncio.Queue()

    async def event_generator():
        queue = _progress_queues[job_id]
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=180.0)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("done", "error"):
                    break
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Timeout'})}\n\n"
                break
        _progress_queues.pop(job_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/meetings/process", status_code=202)
async def process_meeting(request: ProcessMeetingRequest, db: AsyncSession = Depends(get_db)):
    import uuid as _uuid
    from fastapi.responses import StreamingResponse
    import json

    job_id = _uuid.uuid4().hex[:12]
    _progress_queues[job_id] = asyncio.Queue()

    logger.info(f"Processing transcript | len={len(request.transcript)} | job_id={job_id}")
    meeting = Meeting(
        user_id=settings.user_id,
        title=request.title,
        transcript=request.transcript,
        status="processing",
    )
    db.add(meeting)
    await db.flush()
    await db.commit()

    async def run_and_stream():
        from db.database import AsyncSessionLocal
        # First yield job_id immediately
        yield f"data: {json.dumps({'type': 'started', 'job_id': job_id, 'meeting_id': str(meeting.id)})}\n\n"

        async with AsyncSessionLocal() as bg_db:
            try:
                # Run pipeline - progress events go to queue
                pipeline_task = asyncio.create_task(
                    run_meeting_pipeline_custom(
                        bg_db, meeting,
                        progress_queue=_progress_queues.get(job_id)
                    )
                )

                # Stream progress events as they come
                queue = _progress_queues[job_id]
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=180.0)
                        yield f"data: {json.dumps(event)}\n\n"
                        if event.get("type") in ("done", "error"):
                            break
                    except asyncio.TimeoutError:
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Pipeline timeout'})}\n\n"
                        break

                await pipeline_task
                await bg_db.commit()
            except Exception as e:
                await bg_db.rollback()
                logger.error(f"Pipeline failed: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        _progress_queues.pop(job_id, None)

    return StreamingResponse(
        run_and_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/tasks", response_model=AddTaskResponse, status_code=201)
async def add_task(request: AddTaskRequest, db: AsyncSession = Depends(get_db)):
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

    try:
        from tools.calendar_tool import create_task_api
        due = request.deadline if request.deadline else None
        task_result = create_task_api(
            title=request.title,
            due=due,
            notes=f"WorkBrain task. Owner: {request.owner}, Priority: {request.priority}"
        )
        real_task_id = task_result.get("task_id")
        if real_task_id and not str(real_task_id).startswith("mock_"):
            action_item.task_id = real_task_id
            await db.flush()
    except Exception as e:
        logger.warning(f"Google Tasks creation failed: {e}")

    await run_task_pipeline(db, action_item)

    cog_res = await db.execute(
        select(CognitiveState)
        .where(CognitiveState.user_id == settings.user_id, CognitiveState.owner == request.owner)
        .order_by(desc(CognitiveState.calculated_at))
        .limit(1)
    )
    cog = cog_res.scalar_one_or_none()
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


@app.patch("/api/tasks/{task_id}")
async def update_task_status(task_id: str, body: dict, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    import uuid
    try:
        result = await db.execute(
            select(ActionItem).where(
                ActionItem.id == uuid.UUID(task_id),
                ActionItem.user_id == settings.user_id,
            )
        )
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        new_status = body.get("status")
        if new_status not in ["pending", "scheduled", "done", "dropped"]:
            raise HTTPException(status_code=400, detail="Invalid status")
        task.status = new_status
        await db.flush()
        try:
            from agents.adk_runner import recalculate_load_for_owner
            await recalculate_load_for_owner(db, task.owner)
            await db.flush()
        except Exception as ce:
            logger.warning(f"Cognitive recalc failed: {ce}")
        return {"id": str(task.id), "status": task.status, "title": task.title}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tasks/sync-google")
async def sync_google_tasks(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from tools.calendar_tool import _get_credentials
    from googleapiclient.discovery import build
    try:
        result = await db.execute(
            select(ActionItem).where(
                ActionItem.user_id == settings.user_id,
                ActionItem.task_id.isnot(None),
                ActionItem.task_id.notlike("mock_%"),
            )
        )
        wb_tasks = result.scalars().all()
        if not wb_tasks:
            return {"synced": 0, "message": "No tasks with Google Task IDs found"}
        creds = _get_credentials()
        service = build("tasks", "v1", credentials=creds, cache_discovery=False)
        google_tasks_result = service.tasks().list(
            tasklist="@default", maxResults=100, showCompleted=True, showHidden=True,
        ).execute()
        google_tasks = {t["id"]: t for t in google_tasks_result.get("items", [])}
        synced, updates = 0, []
        for task in wb_tasks:
            g_task = google_tasks.get(task.task_id)
            if not g_task:
                continue
            new_status = "done" if g_task.get("status") == "completed" else "pending"
            if task.status != new_status:
                updates.append({"title": task.title, "owner": task.owner, "old_status": task.status, "new_status": new_status})
                task.status = new_status
                synced += 1
        await db.flush()
        if synced > 0:
            from agents.adk_runner import recalculate_load_for_owner
            for owner in list(set(u["owner"] for u in updates)):
                try:
                    await recalculate_load_for_owner(db, owner)
                except Exception as e:
                    logger.warning(f"Recalc failed for {owner}: {e}")
            await db.flush()
        return {"synced": synced, "total_checked": len(wb_tasks), "updates": updates, "message": f"Synced {synced} tasks from Google Tasks"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@app.post("/api/cognitive/recalculate")
async def recalculate_cognitive_load(db: AsyncSession = Depends(get_db)):
    from agents.adk_runner import recalculate_all_owners
    results = await recalculate_all_owners(db)
    recalculated = [r["owner"] for r in results]
    return {"recalculated": recalculated, "message": f"Cognitive load recalculated for {len(recalculated)} owners"}


@app.post("/api/tasks/check-duplicate")
async def check_duplicate_task(body: dict, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from tools.embedding_tool import find_similar_tasks
    title = body.get("title", "")
    if not title:
        return {"similar_tasks": [], "is_duplicate": False}
    result = await db.execute(
        select(ActionItem).where(
            ActionItem.user_id == settings.user_id,
            ActionItem.status.in_(["pending", "scheduled"]),
            ActionItem.embedding.isnot(None),
        )
    )
    existing = result.scalars().all()
    tasks_data = [{"title": t.title, "owner": t.owner, "status": t.status, "embedding": t.embedding} for t in existing]
    similar = find_similar_tasks(title, tasks_data, threshold=0.82)
    return {"similar_tasks": similar[:3], "is_duplicate": len(similar) > 0, "message": f"Found {len(similar)} similar task(s)" if similar else "No duplicates found"}


@app.get("/api/dashboard", response_model=DashboardResponse)
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    uid = settings.user_id
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    mtg_res = await db.execute(select(Meeting).where(Meeting.user_id == uid).order_by(desc(Meeting.created_at)).limit(10))
    meetings = mtg_res.scalars().all()
    cnt_res = await db.execute(select(func.count(Meeting.id)).where(Meeting.user_id == uid, Meeting.created_at >= today_start))
    meetings_today = cnt_res.scalar() or 0
    ai_res = await db.execute(select(ActionItem).where(ActionItem.user_id == uid).order_by(desc(ActionItem.created_at)).limit(20))
    action_items = ai_res.scalars().all()
    cog_res = await db.execute(select(CognitiveState).where(CognitiveState.user_id == uid).order_by(desc(CognitiveState.calculated_at)).limit(200))
    seen_owners: set[str] = set()
    cognitive_states: list[CognitiveState] = []
    for cs in cog_res.scalars().all():
        if cs.owner not in seen_owners:
            seen_owners.add(cs.owner)
            cognitive_states.append(cs)
    overloaded = [cs.owner for cs in cognitive_states if cs.overload_flag]
    user_load = next((cs.load_percentage for cs in cognitive_states if cs.owner in (uid, "demo_user")), 0.0)
    dec_res = await db.execute(select(DecisionLog).where(DecisionLog.user_id == uid).order_by(desc(DecisionLog.timestamp)).limit(15))
    decisions = dec_res.scalars().all()
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


@app.get("/api/meetings", response_model=list[MeetingResponse])
async def list_meetings(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Meeting).where(Meeting.user_id == settings.user_id).order_by(desc(Meeting.created_at)).limit(20))
    return [MeetingResponse.model_validate(m) for m in res.scalars().all()]


@app.get("/api/meetings/{meeting_id}/decisions", response_model=list[DecisionLogResponse])
async def get_meeting_decisions(meeting_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(DecisionLog).where(DecisionLog.user_id == settings.user_id, DecisionLog.meeting_id == meeting_id).order_by(DecisionLog.timestamp))
    decisions = res.scalars().all()
    if not decisions:
        raise HTTPException(status_code=404, detail=f"No decisions found for meeting {meeting_id}")
    return [DecisionLogResponse.model_validate(d) for d in decisions]


@app.get("/api/decisions", response_model=list[DecisionLogResponse])
async def list_decisions(limit: int = 30, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(DecisionLog).where(DecisionLog.user_id == settings.user_id).order_by(desc(DecisionLog.timestamp)).limit(limit))
    return [DecisionLogResponse.model_validate(d) for d in res.scalars().all()]


@app.get("/api/tasks", response_model=list[ActionItemResponse])
async def list_tasks(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(ActionItem).where(ActionItem.user_id == settings.user_id).order_by(desc(ActionItem.created_at)).limit(50))
    return [ActionItemResponse.model_validate(ai) for ai in res.scalars().all()]

    
# ── POST /api/tasks/similar ───────────────────────────────────────────────────
@app.post("/api/tasks/similar")
async def find_similar_tasks(body: dict):
    """Find semantically similar tasks using AlloyDB vector search via MCP Toolbox."""
    title = body.get("title", "")
    if not title:
        return {"similar_tasks": [], "message": "No title provided"}
    try:
        from toolbox_core import ToolboxClient
        client = ToolboxClient("http://localhost:5000")
        tools = await client.load_toolset("workbrain_db_tools")
        search_tool = next(t for t in tools if t._name == "find_similar_tasks")
        result = await search_tool(task_title=title)
        import json
        tasks = json.loads(result) if isinstance(result, str) else result
        await client.close()
        return {
            "similar_tasks": tasks[:3],
            "message": f"Found {len(tasks)} similar tasks via AlloyDB AI similarity search"
        }
    except Exception as e:
        logger.warning(f"Similar tasks search failed: {e}")
        return {"similar_tasks": [], "message": f"Search failed: {str(e)}"}
