from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class ReviewTaskResponse(ORMModel):
    id: int
    task_type: str
    target_type: str
    target_id: str
    status: str
    assigned_to: int | None = None
    priority: str
    review_note: str | None = None
    created_at: datetime


class WorkflowTopicResponse(BaseModel):
    title: str
    source_report: str
    task_type: str
    priority: str
    status: str
