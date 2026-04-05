import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ProcessMeetingRequest(BaseModel):
    transcript: str = Field(..., min_length=10, max_length=50000)
    title: Optional[str] = None


class AddTaskRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    owner: str = Field(default="demo_user")
    duration_minutes: int = Field(default=60, ge=5, le=480)
    priority: int = Field(default=3, ge=1, le=5)
    complexity: int = Field(default=3, ge=1, le=5)
    deadline: Optional[datetime] = None


class MeetingResponse(BaseModel):
    id: uuid.UUID
    user_id: str
    title: Optional[str]
    status: str
    summary: Optional[str]
    processed_at: Optional[datetime]
    created_at: datetime
    action_items_count: int = 0
    decisions_count: int = 0
    model_config = {"from_attributes": True}


class ActionItemResponse(BaseModel):
    id: uuid.UUID
    user_id: str
    meeting_id: Optional[uuid.UUID]
    title: str
    owner: str
    deadline: Optional[datetime]
    priority: int
    complexity: int
    duration_minutes: int
    status: str
    calendar_event_id: Optional[str]
    task_id: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


class CognitiveStateResponse(BaseModel):
    id: uuid.UUID
    owner: str
    load_score: float
    capacity: float
    overload_flag: bool
    context_switches: int
    load_percentage: float
    calculated_at: datetime
    model_config = {"from_attributes": True}


class DecisionLogResponse(BaseModel):
    id: uuid.UUID
    meeting_id: Optional[uuid.UUID]
    agent: str
    decision: str
    reason: str
    metadata: Optional[dict]
    timestamp: datetime
    model_config = {"from_attributes": True}


class DashboardStats(BaseModel):
    meetings_today: int
    total_action_items: int
    user_load_percentage: float
    total_decisions: int
    overloaded_owners: list[str]


class DashboardResponse(BaseModel):
    meetings: list[MeetingResponse]
    action_items: list[ActionItemResponse]
    cognitive_states: list[CognitiveStateResponse]
    decisions: list[DecisionLogResponse]
    stats: DashboardStats


class ProcessMeetingResponse(BaseModel):
    success: bool = True
    message: str
    meeting_id: uuid.UUID
    action_items_created: int
    events_created: int
    tasks_created: int
    overloaded_owners: list[str]
    decisions: list[DecisionLogResponse]


class AddTaskResponse(BaseModel):
    success: bool = True
    message: str
    action_item: ActionItemResponse
    cognitive_state: Optional[CognitiveStateResponse]
    decisions: list[DecisionLogResponse]
