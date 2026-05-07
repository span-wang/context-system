from __future__ import annotations

from sqlalchemy import select

from app.models import ExamPaper, ExamQuestion, MockExam, MockExamQuestion, PracticeSet, PracticeSetQuestion, QuestionBankItem, QuestionSourceLink
from app.repositories.base import Repository


class QuestionBankRepository(Repository):
    def list_bank_questions(self) -> list[QuestionBankItem]:
        return list(self.session.scalars(select(QuestionBankItem).order_by(QuestionBankItem.id.asc())))

    def get_bank_question(self, question_id: int) -> QuestionBankItem | None:
        return self.session.get(QuestionBankItem, question_id)

    def list_practice_sets(self) -> list[PracticeSet]:
        return list(self.session.scalars(select(PracticeSet).order_by(PracticeSet.id.asc())))

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

    def get_paper(self, paper_id: int) -> ExamPaper | None:
        return self.session.get(ExamPaper, paper_id)

    def find_bank_question_by_stem(self, subject_id: int, stem: str) -> QuestionBankItem | None:
        stmt = select(QuestionBankItem).where(
            QuestionBankItem.subject_id == subject_id,
            QuestionBankItem.canonical_stem == stem,
        )
        return self.session.scalar(stmt)

    def has_source_link(self, exam_question_id: int) -> bool:
        stmt = select(QuestionSourceLink.id).where(QuestionSourceLink.exam_question_id == exam_question_id)
        return self.session.scalar(stmt) is not None

    def create_bank_question(self, item: QuestionBankItem) -> QuestionBankItem:
        self.session.add(item)
        self.session.flush()
        return item

    def create_source_link(self, link: QuestionSourceLink) -> QuestionSourceLink:
        self.session.add(link)
        self.session.flush()
        return link

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
