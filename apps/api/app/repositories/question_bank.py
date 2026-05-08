from __future__ import annotations

from sqlalchemy import select

from app.models import (
    ExamPaper,
    ExamQuestion,
    KnowledgePoint,
    MockExam,
    MockExamQuestion,
    PracticeSet,
    PracticeSetQuestion,
    QuestionBankItem,
    QuestionKnowledgeLink,
    QuestionSourceLink,
    Subject,
)
from app.repositories.base import Repository


class QuestionBankRepository(Repository):
    def list_bank_questions(self, include_empty: bool = False) -> list[QuestionBankItem]:
        stmt = select(QuestionBankItem)
        if not include_empty:
            stmt = stmt.where(QuestionBankItem.source_count > 0)
        stmt = stmt.order_by(QuestionBankItem.id.asc())
        return list(self.session.scalars(stmt))

    def get_bank_question(self, question_id: int) -> QuestionBankItem | None:
        return self.session.get(QuestionBankItem, question_id)

    def list_bank_questions_by_ids(self, question_ids: list[int]) -> list[QuestionBankItem]:
        if not question_ids:
            return []
        stmt = select(QuestionBankItem).where(QuestionBankItem.id.in_(question_ids)).order_by(QuestionBankItem.id.asc())
        return list(self.session.scalars(stmt))

    def list_practice_sets(self) -> list[PracticeSet]:
        return list(self.session.scalars(select(PracticeSet).order_by(PracticeSet.id.asc())))

    def get_practice_set(self, practice_set_id: int) -> PracticeSet | None:
        return self.session.get(PracticeSet, practice_set_id)

    def list_practice_set_questions(self, practice_set_id: int) -> list[PracticeSetQuestion]:
        stmt = select(PracticeSetQuestion).where(PracticeSetQuestion.practice_set_id == practice_set_id)
        stmt = stmt.order_by(PracticeSetQuestion.sort_order.asc())
        return list(self.session.scalars(stmt))

    def list_mock_exams(self) -> list[MockExam]:
        return list(self.session.scalars(select(MockExam).order_by(MockExam.id.asc())))

    def list_mock_exam_questions(self, mock_exam_id: int) -> list[MockExamQuestion]:
        stmt = select(MockExamQuestion).where(MockExamQuestion.mock_exam_id == mock_exam_id)
        stmt = stmt.order_by(MockExamQuestion.sort_order.asc())
        return list(self.session.scalars(stmt))

    def list_raw_questions(self, paper_id: int | None = None) -> list[ExamQuestion]:
        stmt = select(ExamQuestion)
        if paper_id is not None:
            stmt = stmt.where(ExamQuestion.paper_id == paper_id)
        stmt = stmt.order_by(ExamQuestion.id.asc())
        return list(self.session.scalars(stmt))

    def list_raw_questions_by_ids(self, question_ids: list[int]) -> list[ExamQuestion]:
        if not question_ids:
            return []
        stmt = select(ExamQuestion).where(ExamQuestion.id.in_(question_ids)).order_by(ExamQuestion.id.asc())
        return list(self.session.scalars(stmt))

    def get_paper(self, paper_id: int) -> ExamPaper | None:
        return self.session.get(ExamPaper, paper_id)

    def list_papers_by_ids(self, paper_ids: list[int]) -> list[ExamPaper]:
        if not paper_ids:
            return []
        stmt = select(ExamPaper).where(ExamPaper.id.in_(paper_ids)).order_by(ExamPaper.id.asc())
        return list(self.session.scalars(stmt))

    def get_subject(self, subject_id: int) -> Subject | None:
        return self.session.get(Subject, subject_id)

    def find_bank_question_by_stem(self, subject_id: int, stem: str) -> QuestionBankItem | None:
        stmt = select(QuestionBankItem).where(
            QuestionBankItem.subject_id == subject_id,
            QuestionBankItem.canonical_stem == stem,
        )
        return self.session.scalar(stmt)

    def has_source_link(self, exam_question_id: int) -> bool:
        stmt = select(QuestionSourceLink.id).where(QuestionSourceLink.exam_question_id == exam_question_id)
        return self.session.scalar(stmt) is not None

    def get_source_link(self, exam_question_id: int) -> QuestionSourceLink | None:
        stmt = select(QuestionSourceLink).where(QuestionSourceLink.exam_question_id == exam_question_id)
        return self.session.scalar(stmt)

    def list_source_links(
        self,
        bank_question_id: int | None = None,
        exam_question_id: int | None = None,
    ) -> list[QuestionSourceLink]:
        stmt = select(QuestionSourceLink)
        if bank_question_id is not None:
            stmt = stmt.where(QuestionSourceLink.bank_question_id == bank_question_id)
        if exam_question_id is not None:
            stmt = stmt.where(QuestionSourceLink.exam_question_id == exam_question_id)
        stmt = stmt.order_by(QuestionSourceLink.id.asc())
        return list(self.session.scalars(stmt))

    def list_source_links_by_bank_question_ids(self, bank_question_ids: list[int]) -> list[QuestionSourceLink]:
        if not bank_question_ids:
            return []
        stmt = (
            select(QuestionSourceLink)
            .where(QuestionSourceLink.bank_question_id.in_(bank_question_ids))
            .order_by(QuestionSourceLink.bank_question_id.asc(), QuestionSourceLink.id.asc())
        )
        return list(self.session.scalars(stmt))

    def list_knowledge_points_by_bank_question_ids(self, bank_question_ids: list[int]) -> dict[int, list[KnowledgePoint]]:
        if not bank_question_ids:
            return {}
        stmt = (
            select(QuestionSourceLink.bank_question_id, KnowledgePoint)
            .join(QuestionKnowledgeLink, QuestionKnowledgeLink.question_id == QuestionSourceLink.exam_question_id)
            .join(KnowledgePoint, KnowledgePoint.id == QuestionKnowledgeLink.knowledge_point_id)
            .where(QuestionSourceLink.bank_question_id.in_(bank_question_ids))
            .order_by(QuestionSourceLink.bank_question_id.asc(), KnowledgePoint.sort_order.asc(), KnowledgePoint.id.asc())
        )
        rows = self.session.execute(stmt).all()
        grouped: dict[int, list[KnowledgePoint]] = {}
        seen: dict[int, set[int]] = {}
        for bank_question_id, point in rows:
            if bank_question_id not in grouped:
                grouped[bank_question_id] = []
                seen[bank_question_id] = set()
            if point.id in seen[bank_question_id]:
                continue
            seen[bank_question_id].add(point.id)
            grouped[bank_question_id].append(point)
        return grouped

    def has_knowledge_links(self, exam_question_id: int) -> bool:
        stmt = select(QuestionKnowledgeLink.id).where(QuestionKnowledgeLink.question_id == exam_question_id)
        return self.session.scalar(stmt) is not None

    def create_bank_question(self, item: QuestionBankItem) -> QuestionBankItem:
        self.session.add(item)
        self.session.flush()
        return item

    def create_source_link(self, link: QuestionSourceLink) -> QuestionSourceLink:
        self.session.add(link)
        self.session.flush()
        return link

    def delete_source_link(self, link: QuestionSourceLink) -> None:
        self.session.delete(link)
        self.session.flush()

    def create_practice_set(self, item: PracticeSet) -> PracticeSet:
        self.session.add(item)
        self.session.flush()
        return item

    def create_practice_set_questions(self, items: list[PracticeSetQuestion]) -> list[PracticeSetQuestion]:
        self.session.add_all(items)
        self.session.flush()
        return items

    def create_mock_exam(self, item: MockExam) -> MockExam:
        self.session.add(item)
        self.session.flush()
        return item

    def create_mock_exam_questions(self, items: list[MockExamQuestion]) -> list[MockExamQuestion]:
        self.session.add_all(items)
        self.session.flush()
        return items
