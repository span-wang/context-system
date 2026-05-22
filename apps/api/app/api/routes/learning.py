from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.auth import CurrentUserResponse
from app.schemas.learning import (
    DailyPlanResponse,
    MasterySnapshotResponse,
    PracticeAnswerReflectionRequest,
    PracticeAnswerSubmitRequest,
    PracticeSessionCreateRequest,
    PracticeSessionDetailResponse,
    PracticeDerivedSessionRequest,
    PracticeResultResponse,
    PracticeSessionSummaryResponse,
    ReviewDueItemResponse,
    WrongBookItemResponse,
)
from app.services.audit import AuditService
from app.services.auth import AuthService
from app.services.learning import LearningService


router = APIRouter(prefix="/api/learning", tags=["learning"])
bearer = HTTPBearer(auto_error=False)


def _current_user(
    credentials: HTTPAuthorizationCredentials | None,
    session: Session,
) -> CurrentUserResponse:
    return AuthService(session).get_current_user(credentials.credentials if credentials else None)


@router.get("/sessions", response_model=list[PracticeSessionSummaryResponse])
def list_learning_sessions(
    limit: int = Query(20, ge=1, le=50),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> list[PracticeSessionSummaryResponse]:
    current_user = _current_user(credentials, session)
    return LearningService(session).list_sessions(current_user, limit=limit)


@router.post("/sessions", response_model=PracticeSessionDetailResponse)
def create_learning_session(
    payload: PracticeSessionCreateRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> PracticeSessionDetailResponse:
    current_user = _current_user(credentials, session)
    result = LearningService(session).create_session(payload, current_user)
    AuditService(session).log(
        current_user,
        module="learning",
        action="create_session",
        target_type="practice_session",
        target_id=result.id,
        payload=payload.model_dump(),
    )
    return result


@router.get("/sessions/{session_id}", response_model=PracticeSessionDetailResponse)
def get_learning_session(
    session_id: int,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> PracticeSessionDetailResponse:
    current_user = _current_user(credentials, session)
    return LearningService(session).get_session_detail(session_id, current_user)


@router.get("/sessions/{session_id}/result", response_model=PracticeResultResponse)
def get_learning_session_result(
    session_id: int,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> PracticeResultResponse:
    current_user = _current_user(credentials, session)
    return LearningService(session).get_session_result(session_id, current_user)


@router.post("/sessions/{session_id}/answer", response_model=PracticeSessionDetailResponse)
def save_learning_answer(
    session_id: int,
    payload: PracticeAnswerSubmitRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> PracticeSessionDetailResponse:
    current_user = _current_user(credentials, session)
    return LearningService(session).save_answer(session_id, payload, current_user)


@router.post("/sessions/{session_id}/reflection", response_model=PracticeResultResponse)
def save_learning_answer_reflection(
    session_id: int,
    payload: PracticeAnswerReflectionRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> PracticeResultResponse:
    current_user = _current_user(credentials, session)
    result = LearningService(session).save_answer_reflection(session_id, payload, current_user)
    AuditService(session).log(
        current_user,
        module="learning",
        action="save_reflection",
        target_type="practice_session",
        target_id=session_id,
        payload=payload.model_dump(),
    )
    return result


@router.post("/sessions/{session_id}/submit", response_model=PracticeSessionDetailResponse)
def submit_learning_session(
    session_id: int,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> PracticeSessionDetailResponse:
    current_user = _current_user(credentials, session)
    result = LearningService(session).submit_session(session_id, current_user)
    AuditService(session).log(
        current_user,
        module="learning",
        action="submit_session",
        target_type="practice_session",
        target_id=result.id,
        payload={
            "correct_count": result.correct_count,
            "total_count": result.total_count,
            "accuracy_rate": result.accuracy_rate,
        },
    )
    return result


@router.get("/wrong-book", response_model=list[WrongBookItemResponse])
def list_wrong_book(
    limit: int = Query(50, ge=1, le=100),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> list[WrongBookItemResponse]:
    current_user = _current_user(credentials, session)
    return LearningService(session).list_wrong_book(current_user, limit=limit)


@router.get("/review-today", response_model=list[ReviewDueItemResponse])
def list_review_today(
    limit: int = Query(20, ge=1, le=100),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> list[ReviewDueItemResponse]:
    current_user = _current_user(credentials, session)
    return LearningService(session).list_review_today(current_user, limit=limit)


@router.post("/review-today/start", response_model=PracticeSessionDetailResponse)
def start_review_today(
    payload: PracticeDerivedSessionRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> PracticeSessionDetailResponse:
    current_user = _current_user(credentials, session)
    result = LearningService(session).create_review_today_session(payload, current_user)
    AuditService(session).log(
        current_user,
        module="learning",
        action="start_review_today",
        target_type="practice_session",
        target_id=result.id,
        payload=payload.model_dump(),
    )
    return result


@router.get("/mastery", response_model=list[MasterySnapshotResponse])
def list_mastery(
    subject_id: int | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> list[MasterySnapshotResponse]:
    current_user = _current_user(credentials, session)
    return LearningService(session).list_mastery(current_user, subject_id=subject_id, limit=limit)


@router.post("/sessions/{session_id}/retry-wrong", response_model=PracticeSessionDetailResponse)
def retry_wrong_questions(
    session_id: int,
    payload: PracticeDerivedSessionRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> PracticeSessionDetailResponse:
    current_user = _current_user(credentials, session)
    result = LearningService(session).create_retry_wrong_session(session_id, payload, current_user)
    AuditService(session).log(
        current_user,
        module="learning",
        action="retry_wrong",
        target_type="practice_session",
        target_id=result.id,
        payload={"source_session_id": session_id, **payload.model_dump()},
    )
    return result


@router.post("/sessions/{session_id}/similar-practice", response_model=PracticeSessionDetailResponse)
def create_similar_practice(
    session_id: int,
    payload: PracticeDerivedSessionRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> PracticeSessionDetailResponse:
    current_user = _current_user(credentials, session)
    result = LearningService(session).create_similar_practice_session(session_id, payload, current_user)
    AuditService(session).log(
        current_user,
        module="learning",
        action="similar_practice",
        target_type="practice_session",
        target_id=result.id,
        payload={"source_session_id": session_id, **payload.model_dump()},
    )
    return result


@router.get("/daily-plan", response_model=DailyPlanResponse)
def get_daily_plan(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> DailyPlanResponse:
    current_user = _current_user(credentials, session)
    return LearningService(session).get_daily_plan(current_user)
