from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session, require_roles
from app.schemas.auth import CurrentUserResponse
from app.schemas.questions import (
    QuestionAiCompleteRequest,
    QuestionAiCompleteResponse,
    QuestionAiKnowledgeReviewRequest,
    QuestionAiKnowledgeReviewResponse,
    QuestionAiProcessRequest,
    QuestionAiProcessResponse,
    QuestionAiReviewRequest,
    QuestionAiReviewResponse,
    QuestionBatchReviewRequest,
    QuestionBatchReviewResponse,
    QuestionDetailResponse,
    QuestionKnowledgeReviewRequest,
    QuestionKnowledgeReviewResponse,
    QuestionPatchRequest,
    QuestionRetagResponse,
    QuestionSummary,
)
from app.services.audit import AuditService
from app.services.questions import QuestionExtractionService


router = APIRouter(prefix="/api/questions", tags=["questions"])


@router.get("", response_model=list[QuestionSummary])
def list_questions(
    paper_id: int | None = Query(default=None),
    review_status: str | None = Query(default=None),
    question_type: str | None = Query(default=None),
    subject_id: int | None = Query(default=None),
    category_id: int | None = Query(default=None),
    year: int | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[QuestionSummary]:
    return QuestionExtractionService(session).list_questions(
        paper_id,
        review_status=review_status,
        question_type=question_type,
        subject_id=subject_id,
        category_id=category_id,
        year=year,
    )


@router.post("/batch-review", response_model=QuestionBatchReviewResponse)
def batch_review_questions(
    payload: QuestionBatchReviewRequest,
    session: Session = Depends(get_session),
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "reviewer")),
) -> QuestionBatchReviewResponse:
    result = QuestionExtractionService(session).batch_review_questions(payload, reviewer_id=current_user.id)
    AuditService(session).log(
        current_user,
        module="questions",
        action="batch_review",
        target_type="question",
        target_id=",".join(str(item) for item in result.question_ids),
        payload={"review_status": result.review_status, "updated_count": result.updated_count, "review_note": payload.review_note},
    )
    return result


@router.post("/ai-complete", response_model=QuestionAiCompleteResponse)
def ai_complete_questions(
    payload: QuestionAiCompleteRequest,
    session: Session = Depends(get_session),
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "reviewer")),
) -> QuestionAiCompleteResponse:
    result = QuestionExtractionService(session).ai_complete_questions(payload, reviewer_id=current_user.id)
    AuditService(session).log(
        current_user,
        module="questions",
        action="ai_complete",
        target_type="question",
        target_id=",".join(str(item) for item in result.question_ids),
        payload={
            "requested_count": result.requested_count,
            "updated_count": result.updated_count,
            "unchanged_count": result.unchanged_count,
            "failed_count": result.failed_count,
            "failed_question_ids": result.failed_question_ids,
        },
    )
    return result


@router.post("/ai-review", response_model=QuestionAiReviewResponse)
def ai_review_questions(
    payload: QuestionAiReviewRequest,
    session: Session = Depends(get_session),
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "reviewer")),
) -> QuestionAiReviewResponse:
    result = QuestionExtractionService(session).ai_review_questions(payload, reviewer_id=current_user.id)
    AuditService(session).log(
        current_user,
        module="questions",
        action="ai_review",
        target_type="question",
        target_id=",".join(str(item) for item in result.question_ids),
        payload={
            "requested_count": result.requested_count,
            "updated_count": result.updated_count,
            "approved_count": result.approved_count,
            "needs_revision_count": result.needs_revision_count,
            "rejected_count": result.rejected_count,
            "failed_count": result.failed_count,
            "failed_question_ids": result.failed_question_ids,
        },
    )
    return result


@router.post("/ai-process", response_model=QuestionAiProcessResponse)
def ai_process_questions(
    payload: QuestionAiProcessRequest,
    session: Session = Depends(get_session),
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "reviewer")),
) -> QuestionAiProcessResponse:
    result = QuestionExtractionService(session).ai_process_questions(payload, reviewer_id=current_user.id)
    AuditService(session).log(
        current_user,
        module="questions",
        action="ai_process",
        target_type="question",
        target_id=",".join(str(item) for item in result.question_ids),
        payload={
            "requested_count": result.requested_count,
            "updated_count": result.updated_count,
            "completed_count": result.completed_count,
            "approved_count": result.approved_count,
            "needs_revision_count": result.needs_revision_count,
            "rejected_count": result.rejected_count,
            "tagged_question_count": result.tagged_question_count,
            "created_link_count": result.created_link_count,
            "failed_count": result.failed_count,
            "failed_question_ids": result.failed_question_ids,
        },
    )
    return result


@router.get("/{question_id}", response_model=QuestionDetailResponse)
def get_question(question_id: int, session: Session = Depends(get_session)) -> QuestionDetailResponse:
    return QuestionExtractionService(session).get_question(question_id)


@router.patch("/{question_id}", response_model=QuestionDetailResponse)
def update_question(
    question_id: int,
    payload: QuestionPatchRequest,
    session: Session = Depends(get_session),
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "reviewer")),
) -> QuestionDetailResponse:
    result = QuestionExtractionService(session).update_question(question_id, payload)
    AuditService(session).log(
        current_user,
        module="questions",
        action="update",
        target_type="question",
        target_id=question_id,
        payload=payload.model_dump(exclude_unset=True),
    )
    return result


@router.post("/{question_id}/knowledge-links/review", response_model=QuestionKnowledgeReviewResponse)
def review_question_knowledge_links(
    question_id: int,
    payload: QuestionKnowledgeReviewRequest,
    session: Session = Depends(get_session),
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "reviewer")),
) -> QuestionKnowledgeReviewResponse:
    result = QuestionExtractionService(session).review_knowledge_links(question_id, payload, reviewer_id=current_user.id)
    AuditService(session).log(
        current_user,
        module="questions",
        action="review_knowledge_links",
        target_type="question",
        target_id=question_id,
        payload={
            "link_ids": result.link_ids,
            "review_status": result.review_status,
            "primary_link_id": result.primary_link_id,
            "updated_count": result.updated_count,
        },
    )
    return result


@router.post("/{question_id}/knowledge-links/ai-review", response_model=QuestionAiKnowledgeReviewResponse)
def ai_review_question_knowledge_links(
    question_id: int,
    payload: QuestionAiKnowledgeReviewRequest,
    session: Session = Depends(get_session),
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "reviewer")),
) -> QuestionAiKnowledgeReviewResponse:
    result = QuestionExtractionService(session).ai_review_knowledge_links(question_id, payload, reviewer_id=current_user.id)
    AuditService(session).log(
        current_user,
        module="questions",
        action="ai_review_knowledge_links",
        target_type="question",
        target_id=question_id,
        payload={
            "link_ids": result.link_ids,
            "updated_count": result.updated_count,
            "approved_count": result.approved_count,
            "rejected_count": result.rejected_count,
            "primary_link_id": result.primary_link_id,
        },
    )
    return result


@router.post("/{question_id}/retag", response_model=QuestionRetagResponse)
def retag_question(
    question_id: int,
    session: Session = Depends(get_session),
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "reviewer")),
) -> QuestionRetagResponse:
    result = QuestionExtractionService(session).retag_question(question_id)
    AuditService(session).log(
        current_user,
        module="questions",
        action="retag",
        target_type="question",
        target_id=question_id,
        payload={"created_links": result.created_links, "total_links": result.total_links},
    )
    return result
