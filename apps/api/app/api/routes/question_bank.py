from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_session, require_roles
from app.schemas.auth import CurrentUserResponse
from app.schemas.question_bank import (
    GenerateMockExamRequest,
    GeneratePracticeSetRequest,
    MockExamResponse,
    PracticeSetDetailResponse,
    PracticeSetResponse,
    QuestionBankItemResponse,
    StandardizeQuestionsRequest,
    StandardizeQuestionsResponse,
)
from app.services.audit import AuditService
from app.services.question_bank import QuestionBankService


router = APIRouter(prefix="/api/question-bank", tags=["question-bank"])


@router.get("/questions", response_model=list[QuestionBankItemResponse])
def list_questions(session: Session = Depends(get_session)) -> list[QuestionBankItemResponse]:
    return QuestionBankService(session).list_questions()


@router.get("/practice-sets", response_model=list[PracticeSetResponse])
def list_practice_sets(session: Session = Depends(get_session)) -> list[PracticeSetResponse]:
    return QuestionBankService(session).list_practice_sets()


@router.get("/practice-sets/{practice_set_id}", response_model=PracticeSetDetailResponse)
def get_practice_set_detail(practice_set_id: int, session: Session = Depends(get_session)) -> PracticeSetDetailResponse:
    return QuestionBankService(session).get_practice_set_detail(practice_set_id)


@router.get("/mock-exams", response_model=list[MockExamResponse])
def list_mock_exams(session: Session = Depends(get_session)) -> list[MockExamResponse]:
    return QuestionBankService(session).list_mock_exams()


@router.post("/standardize", response_model=StandardizeQuestionsResponse)
def standardize_questions(
    payload: StandardizeQuestionsRequest,
    session: Session = Depends(get_session),
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "operator")),
) -> StandardizeQuestionsResponse:
    result = QuestionBankService(session).standardize_questions(payload)
    AuditService(session).log(
        current_user,
        module="question_bank",
        action="standardize",
        target_type="paper",
        target_id=payload.paper_id,
        payload={**payload.model_dump(), **result.model_dump()},
    )
    return result


@router.post("/practice-sets/generate", response_model=PracticeSetResponse)
def generate_practice_set(
    payload: GeneratePracticeSetRequest,
    session: Session = Depends(get_session),
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "operator")),
) -> PracticeSetResponse:
    result = QuestionBankService(session).generate_practice_set(payload)
    AuditService(session).log(
        current_user,
        module="question_bank",
        action="generate_practice_set",
        target_type="practice_set",
        target_id=result.id,
        payload=payload.model_dump(),
    )
    return result


@router.post("/mock-exams/generate", response_model=MockExamResponse)
def generate_mock_exam(
    payload: GenerateMockExamRequest,
    session: Session = Depends(get_session),
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "operator")),
) -> MockExamResponse:
    result = QuestionBankService(session).generate_mock_exam(payload)
    AuditService(session).log(
        current_user,
        module="question_bank",
        action="generate_mock_exam",
        target_type="mock_exam",
        target_id=result.id,
        payload=payload.model_dump(),
    )
    return result
