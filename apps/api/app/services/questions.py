from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import ExamQuestion
from app.repositories.knowledge import KnowledgeRepository
from app.repositories.questions import QuestionRepository
from app.schemas.questions import (
    QuestionBatchReviewRequest,
    QuestionBatchReviewResponse,
    QuestionDetailResponse,
    QuestionKnowledgeLinkResponse,
    QuestionKnowledgeReviewRequest,
    QuestionKnowledgeReviewResponse,
    QuestionPatchRequest,
    QuestionRetagResponse,
    QuestionSummary,
)
from app.services.tagging import apply_rule_tags


class QuestionExtractionService:
    def __init__(self, session: Session) -> None:
        self.repository = QuestionRepository(session)
        self.knowledge_repository = KnowledgeRepository(session)

    def list_questions(
        self,
        paper_id: int | None = None,
        review_status: str | None = None,
        question_type: str | None = None,
    ) -> list[QuestionSummary]:
        return [
            QuestionSummary.model_validate(item)
            for item in self.repository.list_questions(paper_id, review_status=review_status, question_type=question_type)
        ]

    def get_question(self, question_id: int) -> QuestionDetailResponse:
        question = self.repository.get_question(question_id)
        if question is None:
            raise HTTPException(status_code=404, detail="题目不存在")
        return self._detail(question)

    def update_question(self, question_id: int, payload: QuestionPatchRequest) -> QuestionDetailResponse:
        question = self.repository.get_question(question_id)
        if question is None:
            raise HTTPException(status_code=404, detail="题目不存在")
        updates = payload.model_dump(exclude_unset=True)
        for field, value in updates.items():
            if isinstance(value, str):
                value = value.strip()
            setattr(question, field, value)
        if payload.review_status is not None:
            question.reviewed_at = datetime.utcnow()
        question.parse_status = "edited"
        self.repository.session.commit()
        return self._detail(question)

    def batch_review_questions(
        self,
        payload: QuestionBatchReviewRequest,
        reviewer_id: int | None = None,
    ) -> QuestionBatchReviewResponse:
        review_status = payload.review_status.strip()
        if review_status not in {"pending", "approved", "rejected", "needs_revision"}:
            raise HTTPException(status_code=422, detail="不支持的复核状态")

        questions = self.repository.list_questions_by_ids(payload.question_ids)
        found_ids = {item.id for item in questions}
        missing = [item for item in payload.question_ids if item not in found_ids]
        if missing:
            raise HTTPException(status_code=404, detail=f"题目不存在：{missing}")

        review_note = payload.review_note.strip() if payload.review_note else None
        reviewed_at = datetime.utcnow()
        for question in questions:
            question.review_status = review_status
            question.review_note = review_note
            question.reviewed_by = reviewer_id
            question.reviewed_at = reviewed_at

        self.repository.session.commit()
        return QuestionBatchReviewResponse(
            updated_count=len(questions),
            review_status=review_status,
            question_ids=[item.id for item in questions],
        )

    def retag_question(self, question_id: int) -> QuestionRetagResponse:
        question = self.repository.get_question(question_id)
        if question is None:
            raise HTTPException(status_code=404, detail="题目不存在")
        self.repository.delete_rule_links(question.id)
        points = self.knowledge_repository.list_knowledge_points(question.subject_id)
        created = apply_rule_tags(self.repository.session, question, points, question.tenant_id)
        self.repository.session.commit()
        return QuestionRetagResponse(
            question_id=question.id,
            created_links=len(created),
            total_links=len(self.repository.list_links(question.id)),
        )

    def review_knowledge_links(
        self,
        question_id: int,
        payload: QuestionKnowledgeReviewRequest,
        reviewer_id: int | None = None,
    ) -> QuestionKnowledgeReviewResponse:
        question = self.repository.get_question(question_id)
        if question is None:
            raise HTTPException(status_code=404, detail="题目不存在")

        review_status = payload.review_status.strip()
        if review_status not in {"pending", "approved", "rejected"}:
            raise HTTPException(status_code=422, detail="不支持的考点审核状态")
        if payload.primary_link_id is not None and review_status != "approved":
            raise HTTPException(status_code=422, detail="只有确认通过时才允许指定主考点")

        links = self.repository.list_links_by_ids(question_id, payload.link_ids)
        found_ids = {item.id for item in links}
        missing = [item for item in payload.link_ids if item not in found_ids]
        if missing:
            raise HTTPException(status_code=404, detail=f"考点映射不存在：{missing}")
        if payload.primary_link_id is not None and payload.primary_link_id not in found_ids:
            raise HTTPException(status_code=422, detail="主考点必须从本次选中的候选考点中指定")

        all_links = self.repository.list_links(question_id)
        existing_primary_id = next(
            (item.id for item in all_links if item.review_status == "approved" and item.is_primary),
            None,
        )

        resolved_primary_id = payload.primary_link_id
        if review_status == "approved":
            if resolved_primary_id is None:
                resolved_primary_id = existing_primary_id
            if resolved_primary_id is None:
                resolved_primary_id = next((item.id for item in links if item.is_primary), None)
            if resolved_primary_id is None:
                resolved_primary_id = links[0].id

            for item in all_links:
                if item.id != resolved_primary_id and item.is_primary:
                    item.is_primary = False

        reviewed_at = datetime.utcnow()
        for link in links:
            link.review_status = review_status
            link.reviewed_by = reviewer_id
            link.reviewed_at = reviewed_at
            if review_status == "approved":
                link.is_primary = link.id == resolved_primary_id
            elif link.is_primary:
                link.is_primary = False

        if review_status != "approved" and existing_primary_id in found_ids:
            fallback = next(
                (
                    item
                    for item in all_links
                    if item.id not in found_ids and item.review_status == "approved"
                ),
                None,
            )
            if fallback is not None:
                fallback.is_primary = True
                resolved_primary_id = fallback.id
            else:
                resolved_primary_id = None

        self.repository.session.commit()
        return QuestionKnowledgeReviewResponse(
            question_id=question_id,
            updated_count=len(links),
            review_status=review_status,
            link_ids=[item.id for item in links],
            primary_link_id=resolved_primary_id if review_status == "approved" or resolved_primary_id else None,
        )

    def _detail(self, question: ExamQuestion) -> QuestionDetailResponse:
        points = {point.id: point for point in self.knowledge_repository.list_knowledge_points(question.subject_id)}
        links = []
        for link in self.repository.list_links(question.id):
            links.append(
                QuestionKnowledgeLinkResponse.model_validate(
                    {
                        **link.__dict__,
                        "knowledge_point_name": points.get(link.knowledge_point_id).name if points.get(link.knowledge_point_id) else None,
                    }
                )
            )
        return QuestionDetailResponse.model_validate({**question.__dict__, "links": links})
