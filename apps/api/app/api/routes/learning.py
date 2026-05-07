from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_session, require_roles
from app.schemas.auth import CurrentUserResponse
from app.schemas.learning import (
    LearningHomeResponse,
    MasteryResponse,
    PracticeSessionResponse,
    StartPracticeRequest,
    SubmitPracticeRequest,
    WrongBookResponse,
)
from app.schemas.question_bank import PracticeSetResponse
from app.services.audit import AuditService
from app.services.learning import PracticeSessionService


router = APIRouter(prefix="/api/learning", tags=["learning"])


@router.get("/home", response_model=LearningHomeResponse)
def home(session: Session = Depends(get_session)) -> LearningHomeResponse:
    return PracticeSessionService(session).get_home()


@router.get("/practice-sets", response_model=list[PracticeSetResponse])
def practice_sets(session: Session = Depends(get_session)) -> list[PracticeSetResponse]:
    return PracticeSessionService(session).list_practice_sets()


@router.get("/sessions", response_model=list[PracticeSessionResponse])
def sessions(session: Session = Depends(get_session)) -> list[PracticeSessionResponse]:
    return PracticeSessionService(session).list_sessions()


@router.get("/sessions/{session_id}", response_model=PracticeSessionResponse)
def session_detail(session_id: int, session: Session = Depends(get_session)) -> PracticeSessionResponse:
    return PracticeSessionService(session).get_session(session_id)


@router.post("/sessions", response_model=PracticeSessionResponse)
def start_practice(
    payload: StartPracticeRequest,
    session: Session = Depends(get_session),
    current_user: CurrentUserResponse = Depends(require_roles("student", "admin", "teacher")),
) -> PracticeSessionResponse:
    result = PracticeSessionService(session).start_practice(payload)
    AuditService(session).log(
        current_user,
        module="learning",
        action="start_practice",
        target_type="practice_session",
        target_id=result.id,
        payload=payload.model_dump(),
    )
    return result


@router.post("/sessions/{session_id}/submit", response_model=PracticeSessionResponse)
def submit_practice(
    session_id: int,
    payload: SubmitPracticeRequest,
    session: Session = Depends(get_session),
    current_user: CurrentUserResponse = Depends(require_roles("student", "admin", "teacher")),
) -> PracticeSessionResponse:
    result = PracticeSessionService(session).submit_practice(session_id, payload)
    AuditService(session).log(
        current_user,
        module="learning",
        action="submit_practice",
        target_type="practice_session",
        target_id=session_id,
        payload={"answer_count": len(payload.answers), "duration_seconds": payload.duration_seconds},
    )
    return result


@router.get("/wrong-book", response_model=list[WrongBookResponse])
def wrong_book(session: Session = Depends(get_session)) -> list[WrongBookResponse]:
    return PracticeSessionService(session).list_wrong_book()


@router.get("/mastery", response_model=list[MasteryResponse])
def mastery(session: Session = Depends(get_session)) -> list[MasteryResponse]:
    return PracticeSessionService(session).list_mastery()
