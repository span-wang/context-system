from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


BackgroundTaskStatus = Literal["queued", "running", "succeeded", "failed"]


class BackgroundTaskResponse(BaseModel):
    id: str
    task_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: BackgroundTaskStatus
    attempts: int
    max_attempts: int
    last_error: str | None = None
    worker_id: str | None = None
    created_at: datetime
    updated_at: datetime
    next_run_at: datetime
    locked_at: datetime | None = None
    finished_at: datetime | None = None
