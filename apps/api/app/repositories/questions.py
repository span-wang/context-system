from __future__ import annotations

from sqlalchemy import select

from app.models import ExamPaper, ExamQuestion, QuestionKnowledgeLink
from app.repositories.base import Repository


class QuestionRepository(Repository):
    def list_questions(
        self,
        paper_id: int | None = None,
        review_status: str | None = None,
        question_type: str | None = None,
        subject_id: int | None = None,
        category_id: int | None = None,
        year: int | None = None,
    ) -> list[ExamQuestion]:
        stmt = select(ExamQuestion)
        if category_id is not None or year is not None:
            stmt = stmt.join(ExamPaper, ExamPaper.id == ExamQuestion.paper_id)
        if paper_id is not None:
            stmt = stmt.where(ExamQuestion.paper_id == paper_id)
        if review_status is not None:
            stmt = stmt.where(ExamQuestion.review_status == review_status)
        if question_type is not None:
            stmt = stmt.where(ExamQuestion.question_type == question_type)
        if subject_id is not None:
            stmt = stmt.where(ExamQuestion.subject_id == subject_id)
        if category_id is not None:
            stmt = stmt.where(ExamPaper.category_id == category_id)
        if year is not None:
            stmt = stmt.where(ExamPaper.exam_year == year)
        stmt = stmt.order_by(ExamQuestion.id.asc())
        return list(self.session.scalars(stmt))

    def get_question(self, question_id: int) -> ExamQuestion | None:
        return self.session.get(ExamQuestion, question_id)

    def get_paper(self, paper_id: int) -> ExamPaper | None:
        return self.session.get(ExamPaper, paper_id)

    def list_papers_by_ids(self, paper_ids: list[int]) -> list[ExamPaper]:
        if not paper_ids:
            return []
        stmt = select(ExamPaper).where(ExamPaper.id.in_(paper_ids)).order_by(ExamPaper.id.asc())
        return list(self.session.scalars(stmt))

    def list_links(self, question_id: int | None = None) -> list[QuestionKnowledgeLink]:
        stmt = select(QuestionKnowledgeLink)
        if question_id is not None:
            stmt = stmt.where(QuestionKnowledgeLink.question_id == question_id)
        stmt = stmt.order_by(QuestionKnowledgeLink.is_primary.desc(), QuestionKnowledgeLink.id.asc())
        return list(self.session.scalars(stmt))

    def list_links_by_ids(self, question_id: int, link_ids: list[int]) -> list[QuestionKnowledgeLink]:
        if not link_ids:
            return []
        stmt = (
            select(QuestionKnowledgeLink)
            .where(
                QuestionKnowledgeLink.question_id == question_id,
                QuestionKnowledgeLink.id.in_(link_ids),
            )
            .order_by(QuestionKnowledgeLink.id.asc())
        )
        return list(self.session.scalars(stmt))

    def delete_rule_links(self, question_id: int) -> None:
        self.session.query(QuestionKnowledgeLink).filter(
            QuestionKnowledgeLink.question_id == question_id,
            QuestionKnowledgeLink.tag_source.in_(("rule_keyword", "ai_reviewer")),
            QuestionKnowledgeLink.review_status == "pending",
        ).delete(synchronize_session=False)

    def list_questions_by_ids(self, question_ids: list[int]) -> list[ExamQuestion]:
        if not question_ids:
            return []
        stmt = select(ExamQuestion).where(ExamQuestion.id.in_(question_ids)).order_by(ExamQuestion.id.asc())
        return list(self.session.scalars(stmt))
