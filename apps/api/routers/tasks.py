from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from deps import get_db
from schemas.background import BackgroundTaskResponse


router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("", response_model=list[BackgroundTaskResponse])
def list_tasks(limit: int = Query(50, ge=1, le=200)) -> list[BackgroundTaskResponse]:
    return [BackgroundTaskResponse.model_validate(item) for item in get_db().list_background_tasks(limit=limit)]


@router.get("/{task_id}", response_model=BackgroundTaskResponse)
def get_task(task_id: str) -> BackgroundTaskResponse:
    task = get_db().get_background_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="background task not found")
    return BackgroundTaskResponse.model_validate(task)
