from __future__ import annotations

from sqlalchemy import delete, select

from app.models import (
    Asset,
    ExamPaper,
    KnowledgePoint,
    KnowledgePointAlias,
    PaperReviewQuestion,
    PaperReviewQuestionKnowledgePoint,
    PaperSection,
    Subject,
    SubjectCategory,
)
from app.repositories.base import Repository


class PaperReviewRepository(Repository):
    def get_paper(self, paper_id: int) -> ExamPaper | None:
        return self.session.get(ExamPaper, paper_id)

    def get_asset(self, asset_id: int | None) -> Asset | None:
        if asset_id is None:
            return None
        return self.session.get(Asset, asset_id)

    def get_subject(self, subject_id: int | None) -> Subject | None:
        if subject_id is None:
            return None
        return self.session.get(Subject, subject_id)

    def get_category(self, category_id: int | None) -> SubjectCategory | None:
        if category_id is None:
            return None
        return self.session.get(SubjectCategory, category_id)

    def list_sections(self, paper_id: int) -> list[PaperSection]:
        stmt = select(PaperSection).where(PaperSection.paper_id == paper_id).order_by(PaperSection.sort_order.asc(), PaperSection.id.asc())
        return list(self.session.scalars(stmt))

    def list_questions(self, paper_id: int) -> list[PaperReviewQuestion]:
        stmt = (
            select(PaperReviewQuestion)
            .where(PaperReviewQuestion.paper_id == paper_id)
            .order_by(PaperReviewQuestion.sort_order.asc(), PaperReviewQuestion.id.asc())
        )
        return list(self.session.scalars(stmt))

    def get_question(self, question_id: int) -> PaperReviewQuestion | None:
        return self.session.get(PaperReviewQuestion, question_id)

    def get_question_by_fingerprint(self, paper_id: int, content_fingerprint: str) -> PaperReviewQuestion | None:
        stmt = (
            select(PaperReviewQuestion)
            .where(
                PaperReviewQuestion.paper_id == paper_id,
                PaperReviewQuestion.content_fingerprint == content_fingerprint,
            )
            .order_by(PaperReviewQuestion.id.asc())
        )
        return self.session.scalar(stmt)

    def create_question(self, question: PaperReviewQuestion) -> PaperReviewQuestion:
        self.session.add(question)
        self.session.flush()
        return question

    def delete_questions_by_paper(self, paper_id: int) -> int:
        return (
            self.session.query(PaperReviewQuestion)
            .filter(PaperReviewQuestion.paper_id == paper_id)
            .delete(synchronize_session=False)
        )

    def create_questions(self, questions: list[PaperReviewQuestion]) -> list[PaperReviewQuestion]:
        if not questions:
            return questions
        self.session.add_all(questions)
        self.session.flush()
        return questions

    def list_question_knowledge_points(self, question_ids: list[int]) -> list[PaperReviewQuestionKnowledgePoint]:
        if not question_ids:
            return []
        stmt = (
            select(PaperReviewQuestionKnowledgePoint)
            .where(PaperReviewQuestionKnowledgePoint.question_id.in_(question_ids))
            .order_by(
                PaperReviewQuestionKnowledgePoint.rank.asc(),
                PaperReviewQuestionKnowledgePoint.id.asc(),
            )
        )
        return list(self.session.scalars(stmt))

    def replace_question_knowledge_points(
        self,
        question_id: int,
        rows: list[PaperReviewQuestionKnowledgePoint],
    ) -> list[PaperReviewQuestionKnowledgePoint]:
        self.session.execute(
            delete(PaperReviewQuestionKnowledgePoint).where(PaperReviewQuestionKnowledgePoint.question_id == question_id)
        )
        if rows:
            self.session.add_all(rows)
            self.session.flush()
        return rows

    def delete_question_knowledge_points_by_question_ids(self, question_ids: list[int]) -> int:
        if not question_ids:
            return 0
        result = self.session.execute(
            delete(PaperReviewQuestionKnowledgePoint).where(PaperReviewQuestionKnowledgePoint.question_id.in_(question_ids))
        )
        return int(result.rowcount or 0)

    def list_subject_knowledge_points(self, subject_id: int, category_id: int | None = None) -> list[KnowledgePoint]:
        stmt = select(KnowledgePoint).where(KnowledgePoint.subject_id == subject_id)
        if category_id is not None:
            stmt = stmt.where(KnowledgePoint.category_id == category_id)
        stmt = stmt.order_by(KnowledgePoint.sort_order.asc(), KnowledgePoint.id.asc())
        return list(self.session.scalars(stmt))

    def list_knowledge_point_aliases(self, point_ids: list[int]) -> list[KnowledgePointAlias]:
        if not point_ids:
            return []
        stmt = (
            select(KnowledgePointAlias)
            .where(KnowledgePointAlias.knowledge_point_id.in_(point_ids))
            .order_by(KnowledgePointAlias.id.asc())
        )
        return list(self.session.scalars(stmt))
