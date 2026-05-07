from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.workflow import ReviewTaskResponse, WorkflowTopicResponse
from app.services.workflow import AnalysisToTopicService


router = APIRouter(prefix="/api/workflow", tags=["workflow"])


@router.get("/review-tasks", response_model=list[ReviewTaskResponse])
def review_tasks(session: Session = Depends(get_session)) -> list[ReviewTaskResponse]:
    return AnalysisToTopicService(session).list_review_tasks()


@router.get("/topics", response_model=list[WorkflowTopicResponse])
def topics(session: Session = Depends(get_session)) -> list[WorkflowTopicResponse]:
    return AnalysisToTopicService(session).list_topics()
