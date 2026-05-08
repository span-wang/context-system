from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import ExamQuestion
from app.repositories.knowledge import KnowledgeRepository
from app.repositories.questions import QuestionRepository
from app.services.question_bank import QuestionBankService
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
    QuestionKnowledgeLinkResponse,
    QuestionKnowledgeReviewRequest,
    QuestionKnowledgeReviewResponse,
    QuestionPatchRequest,
    QuestionRetagResponse,
    QuestionSummary,
)
from app.services.tagging import apply_rule_tags
from app.services.question_enrichment import (
    apply_ai_tags,
    complete_missing_solution_with_ai,
    normalize_question_fields,
    process_question_with_ai,
    review_knowledge_links_with_ai,
    review_question_with_ai,
)


class QuestionExtractionService:
    def __init__(self, session: Session) -> None:
        self.repository = QuestionRepository(session)
        self.knowledge_repository = KnowledgeRepository(session)

    def list_questions(
        self,
        paper_id: int | None = None,
        review_status: str | None = None,
        question_type: str | None = None,
        subject_id: int | None = None,
        category_id: int | None = None,
        year: int | None = None,
    ) -> list[QuestionSummary]:
        questions = self.repository.list_questions(
            paper_id,
            review_status=review_status,
            question_type=question_type,
            subject_id=subject_id,
            category_id=category_id,
            year=year,
        )
        papers = self.repository.list_papers_by_ids([item.paper_id for item in questions])
        paper_by_id = {item.id: item for item in papers}
        return [
            QuestionSummary.model_validate(
                {
                    **item.__dict__,
                    **_question_source_fields(item, paper_by_id.get(item.paper_id)),
                }
            )
            for item in questions
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
        if updates:
            QuestionBankService(self.repository.session).sync_question_to_bank(question, publish=True)
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
        bank_service = QuestionBankService(self.repository.session)
        for question in questions:
            question.review_status = review_status
            question.review_note = review_note
            question.reviewed_by = reviewer_id
            question.reviewed_at = reviewed_at
            bank_service.sync_question_to_bank(question, publish=True)

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
        normalize_question_fields(question)
        self.repository.delete_rule_links(question.id)
        points = self.knowledge_repository.list_knowledge_points(question.subject_id)
        created = apply_rule_tags(self.repository.session, question, points, question.tenant_id)
        ai_created = []
        if not created:
            ai_created = apply_ai_tags(self.repository.session, question, points, question.tenant_id)
        self.repository.session.commit()
        return QuestionRetagResponse(
            question_id=question.id,
            created_links=len(created) + len(ai_created),
            ai_created_links=len(ai_created),
            total_links=len(self.repository.list_links(question.id)),
        )

    def ai_complete_questions(
        self,
        payload: QuestionAiCompleteRequest,
        reviewer_id: int | None = None,
    ) -> QuestionAiCompleteResponse:
        questions = self.repository.list_questions_by_ids(payload.question_ids)
        found_ids = {item.id for item in questions}
        missing = [item for item in payload.question_ids if item not in found_ids]
        if missing:
            raise HTTPException(status_code=404, detail=f"题目不存在：{missing}")

        subject_names: dict[int, str | None] = {}
        updated_count = 0
        unchanged_count = 0
        failed_ids: list[int] = []
        reviewed_at = datetime.utcnow()

        for question in questions:
            normalize_question_fields(question)
            subject_name = subject_names.get(question.subject_id)
            if question.subject_id not in subject_names:
                subject = self.knowledge_repository.get_subject(question.subject_id)
                subject_name = subject.name if subject else None
                subject_names[question.subject_id] = subject_name
            result = complete_missing_solution_with_ai(question, subject_name=subject_name)
            if result.changed:
                question.reviewed_by = reviewer_id
                question.reviewed_at = reviewed_at
                updated_count += 1
                continue
            if result.error:
                failed_ids.append(question.id)
                continue
            unchanged_count += 1

        self.repository.session.commit()
        failed_count = len(failed_ids)
        return QuestionAiCompleteResponse(
            requested_count=len(payload.question_ids),
            updated_count=updated_count,
            unchanged_count=unchanged_count,
            failed_count=failed_count,
            question_ids=[item.id for item in questions],
            failed_question_ids=failed_ids,
            message=(
                f"AI补全完成：更新 {updated_count} 道，未变更 {unchanged_count} 道"
                + (f"，失败 {failed_count} 道" if failed_count else "")
            ),
        )

    def ai_review_questions(
        self,
        payload: QuestionAiReviewRequest,
        reviewer_id: int | None = None,
    ) -> QuestionAiReviewResponse:
        questions = self.repository.list_questions_by_ids(payload.question_ids)
        found_ids = {item.id for item in questions}
        missing = [item for item in payload.question_ids if item not in found_ids]
        if missing:
            raise HTTPException(status_code=404, detail=f"题目不存在：{missing}")

        subject_names: dict[int, str | None] = {}
        reviewed_at = datetime.utcnow()
        updated_count = 0
        approved_count = 0
        needs_revision_count = 0
        rejected_count = 0
        failed_ids: list[int] = []
        bank_service = QuestionBankService(self.repository.session)
        for question in questions:
            if question.subject_id not in subject_names:
                subject = self.knowledge_repository.get_subject(question.subject_id)
                subject_names[question.subject_id] = subject.name if subject else None
            result = review_question_with_ai(question, subject_name=subject_names[question.subject_id])
            if result.error or not result.review_status:
                failed_ids.append(question.id)
                continue
            question.review_status = result.review_status
            question.review_note = result.review_note
            question.reviewed_by = reviewer_id
            question.reviewed_at = reviewed_at
            bank_service.sync_question_to_bank(question, publish=True)
            updated_count += 1
            if result.review_status == "approved":
                approved_count += 1
            elif result.review_status == "needs_revision":
                needs_revision_count += 1
            elif result.review_status == "rejected":
                rejected_count += 1

        self.repository.session.commit()
        failed_count = len(failed_ids)
        return QuestionAiReviewResponse(
            requested_count=len(payload.question_ids),
            updated_count=updated_count,
            approved_count=approved_count,
            needs_revision_count=needs_revision_count,
            rejected_count=rejected_count,
            failed_count=failed_count,
            question_ids=[item.id for item in questions],
            failed_question_ids=failed_ids,
            message=(
                f"AI复核完成：通过 {approved_count} 道，待修订 {needs_revision_count} 道，退回 {rejected_count} 道"
                + (f"，失败 {failed_count} 道" if failed_count else "")
            ),
        )

    def ai_process_questions(
        self,
        payload: QuestionAiProcessRequest,
        reviewer_id: int | None = None,
    ) -> QuestionAiProcessResponse:
        questions = self.repository.list_questions_by_ids(payload.question_ids)
        found_ids = {item.id for item in questions}
        missing = [item for item in payload.question_ids if item not in found_ids]
        if missing:
            raise HTTPException(status_code=404, detail=f"题目不存在：{missing}")

        subject_names: dict[int, str | None] = {}
        updated_count = 0
        completed_count = 0
        approved_count = 0
        needs_revision_count = 0
        rejected_count = 0
        tagged_question_count = 0
        created_link_count = 0
        failed_ids: list[int] = []
        reviewed_at = datetime.utcnow()

        for question in questions:
            normalize_question_fields(question)
            if question.subject_id not in subject_names:
                subject = self.knowledge_repository.get_subject(question.subject_id)
                subject_names[question.subject_id] = subject.name if subject else None
            points = self.knowledge_repository.list_knowledge_points(question.subject_id)
            result = process_question_with_ai(
                self.repository.session,
                question,
                points,
                question.tenant_id,
                reviewer_id,
                subject_name=subject_names[question.subject_id],
            )
            if result.error:
                failed_ids.append(question.id)
                continue
            completed_count += 1
            if result.changed:
                updated_count += 1
            if result.created_links:
                tagged_question_count += 1
                created_link_count += result.created_links
            if result.review_status == "approved":
                approved_count += 1
            elif result.review_status == "needs_revision":
                needs_revision_count += 1
            elif result.review_status == "rejected":
                rejected_count += 1
            question.reviewed_by = reviewer_id
            question.reviewed_at = reviewed_at

        self.repository.session.commit()
        failed_count = len(failed_ids)
        return QuestionAiProcessResponse(
            requested_count=len(payload.question_ids),
            updated_count=updated_count,
            completed_count=completed_count,
            approved_count=approved_count,
            needs_revision_count=needs_revision_count,
            rejected_count=rejected_count,
            tagged_question_count=tagged_question_count,
            created_link_count=created_link_count,
            failed_count=failed_count,
            question_ids=[item.id for item in questions],
            failed_question_ids=failed_ids,
            message=(
                f"AI综合处理完成：补全更新 {updated_count} 道，确认考点 {tagged_question_count} 道，通过 {approved_count} 道，待修订 {needs_revision_count} 道，退回 {rejected_count} 道"
                + (f"，失败 {failed_count} 道" if failed_count else "")
            ),
        )

    def ai_review_knowledge_links(
        self,
        question_id: int,
        payload: QuestionAiKnowledgeReviewRequest,
        reviewer_id: int | None = None,
    ) -> QuestionAiKnowledgeReviewResponse:
        question = self.repository.get_question(question_id)
        if question is None:
            raise HTTPException(status_code=404, detail="题目不存在")

        links = self.repository.list_links_by_ids(question_id, payload.link_ids)
        found_ids = {item.id for item in links}
        missing = [item for item in payload.link_ids if item not in found_ids]
        if missing:
            raise HTTPException(status_code=404, detail=f"考点映射不存在：{missing}")

        all_links = self.repository.list_links(question_id)
        point_by_id = {point.id: point for point in self.knowledge_repository.list_knowledge_points(question.subject_id)}
        result = review_knowledge_links_with_ai(question, links, point_by_id)
        if result.error:
            raise HTTPException(status_code=422, detail="AI考点审核失败")

        reviewed_at = datetime.utcnow()
        for link in all_links:
            if link.id in result.approved_link_ids:
                link.review_status = "approved"
                link.reviewed_by = reviewer_id
                link.reviewed_at = reviewed_at
                link.is_primary = link.id == result.primary_link_id
            elif link.id in result.rejected_link_ids:
                link.review_status = "rejected"
                link.reviewed_by = reviewer_id
                link.reviewed_at = reviewed_at
                link.is_primary = False

        self.repository.session.commit()
        approved_count = len(result.approved_link_ids)
        rejected_count = len(result.rejected_link_ids)
        return QuestionAiKnowledgeReviewResponse(
            question_id=question_id,
            updated_count=approved_count + rejected_count,
            approved_count=approved_count,
            rejected_count=rejected_count,
            link_ids=[*result.approved_link_ids, *result.rejected_link_ids],
            primary_link_id=result.primary_link_id,
            message=(
                f"AI考点审核完成：确认 {approved_count} 条，退回 {rejected_count} 条"
                + (f"，主考点 #{result.primary_link_id}" if result.primary_link_id else "")
            ),
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
        paper = self.repository.get_paper(question.paper_id)
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
        return QuestionDetailResponse.model_validate(
            {
                **question.__dict__,
                **_question_source_fields(question, paper),
                "links": links,
            }
        )


def _question_source_fields(question: ExamQuestion, paper) -> dict[str, str | int | None]:
    paper_name = paper.paper_name if paper else None
    question_no = str(question.question_no or "").strip() or "-"
    return {
        "paper_name": paper_name,
        "source_label": f"{paper_name} · 第{question_no}题" if paper_name else None,
        "source_year": paper.exam_year if paper else None,
        "source_region": paper.exam_region if paper else None,
    }
