from __future__ import annotations

from sqlalchemy import and_, case, delete, func, literal, or_, select
from sqlalchemy.orm import aliased

from app.models import (
    ExamPaper,
    Chapter,
    KnowledgePoint,
    PaperReviewQuestion,
    PaperReviewQuestionKnowledgePoint,
    QuestionBankItem,
    QuestionBankSourceLink,
    Subject,
    SubjectCategory,
)
from app.repositories.base import Repository


class QuestionBankRepository(Repository):
    def get_question(self, question_id: int) -> QuestionBankItem | None:
        return self.session.get(QuestionBankItem, question_id)

    def get_review_question(self, question_id: int) -> PaperReviewQuestion | None:
        return self.session.get(PaperReviewQuestion, question_id)

    def list_review_questions(self, paper_id: int) -> list[PaperReviewQuestion]:
        stmt = (
            select(PaperReviewQuestion)
            .where(PaperReviewQuestion.paper_id == paper_id)
            .order_by(PaperReviewQuestion.sort_order.asc(), PaperReviewQuestion.id.asc())
        )
        return list(self.session.scalars(stmt))

    def get_paper(self, paper_id: int | None) -> ExamPaper | None:
        if paper_id is None:
            return None
        return self.session.get(ExamPaper, paper_id)

    def get_subject(self, subject_id: int | None) -> Subject | None:
        if subject_id is None:
            return None
        return self.session.get(Subject, subject_id)

    def get_category(self, category_id: int | None) -> SubjectCategory | None:
        if category_id is None:
            return None
        return self.session.get(SubjectCategory, category_id)

    def get_by_fingerprint(self, content_fingerprint: str) -> QuestionBankItem | None:
        stmt = select(QuestionBankItem).where(QuestionBankItem.content_fingerprint == content_fingerprint)
        return self.session.scalar(stmt)

    def get_source_link(self, source_type: str, source_question_id: int) -> QuestionBankSourceLink | None:
        stmt = select(QuestionBankSourceLink).where(
            QuestionBankSourceLink.source_type == source_type,
            QuestionBankSourceLink.source_question_id == source_question_id,
        )
        return self.session.scalar(stmt)

    def create_question(self, question: QuestionBankItem) -> QuestionBankItem:
        self.session.add(question)
        self.session.flush()
        return question

    def create_source_link(self, link: QuestionBankSourceLink) -> QuestionBankSourceLink:
        self.session.add(link)
        self.session.flush()
        return link

    def list_child_questions(self, parent_ids: list[int]) -> list[QuestionBankItem]:
        if not parent_ids:
            return []
        stmt = (
            select(QuestionBankItem)
            .where(QuestionBankItem.parent_question_id.in_(parent_ids))
            .order_by(QuestionBankItem.id.asc())
        )
        return list(self.session.scalars(stmt))

    def delete_source_links_by_bank_question(self, bank_question_id: int) -> int:
        result = self.session.execute(
            delete(QuestionBankSourceLink).where(QuestionBankSourceLink.bank_question_id == bank_question_id)
        )
        return int(result.rowcount or 0)

    def delete_source_links_by_bank_question_ids(self, bank_question_ids: list[int]) -> int:
        if not bank_question_ids:
            return 0
        result = self.session.execute(
            delete(QuestionBankSourceLink).where(QuestionBankSourceLink.bank_question_id.in_(bank_question_ids))
        )
        return int(result.rowcount or 0)

    def delete_question(self, question: QuestionBankItem) -> None:
        self.session.delete(question)

    def count_sources(self, bank_question_id: int) -> int:
        stmt = select(func.count(QuestionBankSourceLink.id)).where(
            QuestionBankSourceLink.bank_question_id == bank_question_id,
            QuestionBankSourceLink.status == "active",
        )
        return int(self.session.scalar(stmt) or 0)

    def list_questions(
        self,
        *,
        subject_id: int | None = None,
        category_id: int | None = None,
        status: str | None = None,
        question_type: str | None = None,
        keyword: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[tuple[QuestionBankItem, Subject | None, SubjectCategory | None, ExamPaper | None]], int]:
        filters = self._question_filters(subject_id, category_id, status, question_type, keyword)
        base_stmt = select(QuestionBankItem).where(QuestionBankItem.parent_question_id.is_(None), *filters)
        total = int(self.session.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0)
        stmt = (
            select(QuestionBankItem, Subject, SubjectCategory, ExamPaper)
            .join(Subject, QuestionBankItem.subject_id == Subject.id, isouter=True)
            .join(SubjectCategory, QuestionBankItem.category_id == SubjectCategory.id, isouter=True)
            .join(PaperReviewQuestion, QuestionBankItem.first_source_question_id == PaperReviewQuestion.id, isouter=True)
            .join(ExamPaper, PaperReviewQuestion.paper_id == ExamPaper.id, isouter=True)
            .where(QuestionBankItem.parent_question_id.is_(None), *filters)
            .order_by(QuestionBankItem.updated_at.desc(), QuestionBankItem.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.execute(stmt).all()), total

    def count_by_status(self) -> dict[str, int]:
        stmt = (
            select(QuestionBankItem.status, func.count(QuestionBankItem.id))
            .where(QuestionBankItem.parent_question_id.is_(None))
            .group_by(QuestionBankItem.status)
        )
        return {str(status): int(count) for status, count in self.session.execute(stmt).all()}

    def list_sources(
        self,
        bank_question_id: int,
    ) -> list[tuple[QuestionBankSourceLink, PaperReviewQuestion | None, ExamPaper | None]]:
        return self.list_sources_by_bank_question_ids([bank_question_id])

    def list_sources_by_bank_question_ids(
        self,
        bank_question_ids: list[int],
    ) -> list[tuple[QuestionBankSourceLink, PaperReviewQuestion | None, ExamPaper | None]]:
        if not bank_question_ids:
            return []
        stmt = (
            select(QuestionBankSourceLink, PaperReviewQuestion, ExamPaper)
            .join(PaperReviewQuestion, QuestionBankSourceLink.source_question_id == PaperReviewQuestion.id, isouter=True)
            .join(ExamPaper, QuestionBankSourceLink.paper_id == ExamPaper.id, isouter=True)
            .where(QuestionBankSourceLink.bank_question_id.in_(bank_question_ids))
            .order_by(QuestionBankSourceLink.created_at.asc(), QuestionBankSourceLink.id.asc())
        )
        return list(self.session.execute(stmt).all())

    def list_export_papers(
        self,
        *,
        subject_id: int | None = None,
        category_id: int | None = None,
        status: str | None = None,
        question_type: str | None = None,
        keyword: str | None = None,
    ) -> list[tuple[ExamPaper, Subject | None, SubjectCategory | None, int]]:
        filters = self._question_filters(subject_id, category_id, status, question_type, keyword)
        stmt = (
            select(
                ExamPaper,
                Subject,
                SubjectCategory,
                func.count(QuestionBankSourceLink.id).label("question_count"),
            )
            .join(QuestionBankSourceLink, QuestionBankSourceLink.paper_id == ExamPaper.id)
            .join(QuestionBankItem, QuestionBankSourceLink.bank_question_id == QuestionBankItem.id)
            .join(Subject, ExamPaper.subject_id == Subject.id, isouter=True)
            .join(SubjectCategory, ExamPaper.category_id == SubjectCategory.id, isouter=True)
            .where(
                QuestionBankSourceLink.status == "active",
                QuestionBankItem.parent_question_id.is_(None),
                *filters,
            )
            .group_by(ExamPaper.id, Subject.id, SubjectCategory.id)
            .order_by(
                func.coalesce(ExamPaper.exam_year, 0).desc(),
                ExamPaper.id.desc(),
            )
        )
        rows = self.session.execute(stmt).all()
        return [(paper, subject, category, int(question_count or 0)) for paper, subject, category, question_count in rows]

    def list_export_rows(
        self,
        *,
        paper_id: int,
        subject_id: int | None = None,
        category_id: int | None = None,
        status: str | None = None,
        question_type: str | None = None,
        keyword: str | None = None,
    ) -> list[tuple[QuestionBankSourceLink, QuestionBankItem, PaperReviewQuestion, ExamPaper]]:
        filters = self._question_filters(subject_id, category_id, status, question_type, keyword)
        stmt = (
            select(QuestionBankSourceLink, QuestionBankItem, PaperReviewQuestion, ExamPaper)
            .join(QuestionBankItem, QuestionBankSourceLink.bank_question_id == QuestionBankItem.id)
            .join(PaperReviewQuestion, QuestionBankSourceLink.source_question_id == PaperReviewQuestion.id)
            .join(ExamPaper, QuestionBankSourceLink.paper_id == ExamPaper.id)
            .where(
                QuestionBankSourceLink.paper_id == paper_id,
                QuestionBankSourceLink.status == "active",
                QuestionBankItem.parent_question_id.is_(None),
                *filters,
            )
            .order_by(
                PaperReviewQuestion.sort_order.asc(),
                PaperReviewQuestion.id.asc(),
                QuestionBankSourceLink.id.asc(),
            )
        )
        return list(self.session.execute(stmt).all())

    def list_review_question_tags(self, question_id: int) -> list[tuple[PaperReviewQuestionKnowledgePoint, KnowledgePoint]]:
        stmt = (
            select(PaperReviewQuestionKnowledgePoint, KnowledgePoint)
            .join(KnowledgePoint, PaperReviewQuestionKnowledgePoint.knowledge_point_id == KnowledgePoint.id)
            .where(PaperReviewQuestionKnowledgePoint.question_id == question_id)
            .order_by(
                case(
                    (PaperReviewQuestionKnowledgePoint.status == "confirmed", 0),
                    (PaperReviewQuestionKnowledgePoint.status == "suggested", 1),
                    else_=2,
                ).asc(),
                PaperReviewQuestionKnowledgePoint.rank.asc(),
                PaperReviewQuestionKnowledgePoint.id.asc(),
            )
        )
        return list(self.session.execute(stmt).all())

    def list_knowledge_analysis_rows(
        self,
        *,
        subject_id: int | None = None,
        category_id: int | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
    ) -> list[tuple[QuestionBankItem, QuestionBankSourceLink, PaperReviewQuestion, ExamPaper, KnowledgePoint | None]]:
        primary_tag_subquery = (
            select(
                PaperReviewQuestionKnowledgePoint.question_id.label("question_id"),
                func.coalesce(
                    func.min(
                        case(
                            (
                                PaperReviewQuestionKnowledgePoint.status == "confirmed",
                                PaperReviewQuestionKnowledgePoint.id,
                            )
                        )
                    ),
                    func.min(
                        case(
                            (
                                PaperReviewQuestionKnowledgePoint.status == "suggested",
                                PaperReviewQuestionKnowledgePoint.id,
                            )
                        )
                    ),
                ).label("tag_id"),
            )
            .where(
                PaperReviewQuestionKnowledgePoint.status.in_(["confirmed", "suggested"]),
                PaperReviewQuestionKnowledgePoint.relation_type == "primary",
            )
            .group_by(PaperReviewQuestionKnowledgePoint.question_id)
            .subquery()
        )
        stmt = (
            select(
                QuestionBankItem,
                QuestionBankSourceLink,
                PaperReviewQuestion,
                ExamPaper,
                KnowledgePoint,
            )
            .join(QuestionBankSourceLink, QuestionBankSourceLink.bank_question_id == QuestionBankItem.id)
            .join(PaperReviewQuestion, QuestionBankSourceLink.source_question_id == PaperReviewQuestion.id)
            .join(ExamPaper, QuestionBankSourceLink.paper_id == ExamPaper.id)
            .join(
                primary_tag_subquery,
                primary_tag_subquery.c.question_id == PaperReviewQuestion.id,
                isouter=True,
            )
            .join(
                PaperReviewQuestionKnowledgePoint,
                PaperReviewQuestionKnowledgePoint.id == primary_tag_subquery.c.tag_id,
                isouter=True,
            )
            .join(KnowledgePoint, KnowledgePoint.id == PaperReviewQuestionKnowledgePoint.knowledge_point_id, isouter=True)
            .join(Chapter, Chapter.id == KnowledgePoint.chapter_id, isouter=True)
            .where(
                QuestionBankItem.status == "active",
                QuestionBankItem.node_role != "group",
                QuestionBankSourceLink.status == "active",
                ExamPaper.paper_type == "真题",
            )
            .order_by(
                func.coalesce(ExamPaper.exam_year, 0).asc(),
                ExamPaper.id.asc(),
                QuestionBankSourceLink.id.asc(),
            )
        )
        filters = []
        if subject_id is not None:
            filters.append(ExamPaper.subject_id == subject_id)
        if category_id is not None:
            filters.append(ExamPaper.category_id == category_id)
        if start_year is not None:
            filters.append(and_(ExamPaper.exam_year.is_not(None), ExamPaper.exam_year >= start_year))
        if end_year is not None:
            filters.append(and_(ExamPaper.exam_year.is_not(None), ExamPaper.exam_year <= end_year))
        if filters:
            stmt = stmt.where(*filters)
        return list(self.session.execute(stmt).all())

    def _question_filters(
        self,
        subject_id: int | None,
        category_id: int | None,
        status: str | None,
        question_type: str | None,
        keyword: str | None,
    ) -> list:
        filters = []
        if subject_id is not None:
            filters.append(QuestionBankItem.subject_id == subject_id)
        if category_id is not None:
            filters.append(QuestionBankItem.category_id == category_id)
        if status:
            filters.append(QuestionBankItem.status == status)
        if question_type:
            filters.append(QuestionBankItem.question_type == question_type)
        if keyword:
            like_keyword = f"%{keyword}%"
            child_question = aliased(QuestionBankItem)
            child_match = (
                select(child_question.id)
                .where(
                    child_question.parent_question_id == QuestionBankItem.id,
                    or_(
                        child_question.stem_text.like(like_keyword),
                        func.coalesce(child_question.answer_text, literal("")).like(like_keyword),
                        func.coalesce(child_question.analysis_text, literal("")).like(like_keyword),
                    ),
                )
                .limit(1)
            )
            filters.append(
                or_(
                    QuestionBankItem.stem_text.like(like_keyword),
                    func.coalesce(QuestionBankItem.group_stem, literal("")).like(like_keyword),
                    func.coalesce(QuestionBankItem.material_text, literal("")).like(like_keyword),
                    func.coalesce(QuestionBankItem.answer_text, literal("")).like(like_keyword),
                    func.coalesce(QuestionBankItem.analysis_text, literal("")).like(like_keyword),
                    child_match.exists(),
                )
            )
        return filters
