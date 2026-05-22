from __future__ import annotations

from sqlalchemy import and_, desc, func, select

from app.models import (
    Chapter,
    ExamPaper,
    KnowledgePoint,
    MasterySnapshot,
    PaperReviewQuestion,
    PaperReviewQuestionKnowledgePoint,
    PracticeAnswer,
    PracticeSession,
    PracticeSessionItem,
    QuestionBankItem,
    QuestionBankSourceLink,
    Subject,
    SubjectCategory,
    WrongBookItem,
)
from app.repositories.base import Repository


class LearningRepository(Repository):
    def get_session(self, session_id: int) -> PracticeSession | None:
        return self.session.get(PracticeSession, session_id)

    def get_session_item(self, item_id: int) -> PracticeSessionItem | None:
        return self.session.get(PracticeSessionItem, item_id)

    def list_sessions(self, user_id: int, limit: int) -> list[PracticeSession]:
        stmt = (
            select(PracticeSession)
            .where(PracticeSession.user_id == user_id)
            .order_by(PracticeSession.created_at.desc(), PracticeSession.id.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def create_session(self, session_item: PracticeSession) -> PracticeSession:
        self.session.add(session_item)
        self.session.flush()
        return session_item

    def create_session_items(self, items: list[PracticeSessionItem]) -> None:
        if not items:
            return
        self.session.add_all(items)
        self.session.flush()

    def list_session_items(self, session_id: int) -> list[PracticeSessionItem]:
        stmt = (
            select(PracticeSessionItem)
            .where(PracticeSessionItem.session_id == session_id)
            .order_by(PracticeSessionItem.sort_order.asc(), PracticeSessionItem.id.asc())
        )
        return list(self.session.scalars(stmt))

    def list_answers(self, session_id: int) -> list[PracticeAnswer]:
        stmt = (
            select(PracticeAnswer)
            .where(PracticeAnswer.session_id == session_id)
            .order_by(PracticeAnswer.id.asc())
        )
        return list(self.session.scalars(stmt))

    def get_answer_by_item(self, session_item_id: int) -> PracticeAnswer | None:
        stmt = select(PracticeAnswer).where(PracticeAnswer.session_item_id == session_item_id)
        return self.session.scalar(stmt)

    def create_answer(self, answer: PracticeAnswer) -> PracticeAnswer:
        self.session.add(answer)
        self.session.flush()
        return answer

    def list_wrong_book_items(self, user_id: int, limit: int, *, mastered: bool | None = None) -> list[WrongBookItem]:
        stmt = select(WrongBookItem).where(WrongBookItem.user_id == user_id)
        if mastered is not None:
            stmt = stmt.where(WrongBookItem.mastered == mastered)
        stmt = stmt.order_by(
            WrongBookItem.mastered.asc(),
            WrongBookItem.wrong_count.desc(),
            desc(WrongBookItem.last_wrong_at),
            desc(WrongBookItem.updated_at),
        ).limit(limit)
        return list(self.session.scalars(stmt))

    def get_wrong_book_item(self, user_id: int, bank_question_id: int | None) -> WrongBookItem | None:
        if bank_question_id is None:
            return None
        stmt = select(WrongBookItem).where(
            WrongBookItem.user_id == user_id,
            WrongBookItem.bank_question_id == bank_question_id,
        )
        return self.session.scalar(stmt)

    def create_wrong_book_item(self, item: WrongBookItem) -> WrongBookItem:
        self.session.add(item)
        self.session.flush()
        return item

    def get_mastery_snapshot(self, user_id: int, knowledge_point_id: int) -> MasterySnapshot | None:
        stmt = select(MasterySnapshot).where(
            MasterySnapshot.user_id == user_id,
            MasterySnapshot.knowledge_point_id == knowledge_point_id,
        )
        return self.session.scalar(stmt)

    def create_mastery_snapshot(self, item: MasterySnapshot) -> MasterySnapshot:
        self.session.add(item)
        self.session.flush()
        return item

    def list_mastery_rows(
        self,
        user_id: int,
        *,
        subject_id: int | None = None,
        knowledge_point_ids: list[int] | None = None,
        limit: int = 20,
    ) -> list[tuple[MasterySnapshot, KnowledgePoint]]:
        stmt = (
            select(MasterySnapshot, KnowledgePoint)
            .join(KnowledgePoint, KnowledgePoint.id == MasterySnapshot.knowledge_point_id)
            .where(MasterySnapshot.user_id == user_id)
        )
        if subject_id is not None:
            stmt = stmt.where(MasterySnapshot.subject_id == subject_id)
        if knowledge_point_ids:
            stmt = stmt.where(MasterySnapshot.knowledge_point_id.in_(knowledge_point_ids))
        stmt = stmt.order_by(
            MasterySnapshot.mastery_score.asc(),
            desc(MasterySnapshot.answered_count),
            MasterySnapshot.id.asc(),
        ).limit(limit)
        return list(self.session.execute(stmt).all())

    def list_candidate_questions(
        self,
        *,
        session_type: str,
        user_id: int,
        subject_id: int | None = None,
        category_id: int | None = None,
        chapter_id: int | None = None,
        paper_id: int | None = None,
        question_type: str | None = None,
    ) -> list[QuestionBankItem]:
        stmt = select(QuestionBankItem).where(
            QuestionBankItem.status == "active",
            QuestionBankItem.node_role != "group",
        )

        if subject_id is not None:
            stmt = stmt.where(QuestionBankItem.subject_id == subject_id)
        if category_id is not None:
            stmt = stmt.where(QuestionBankItem.category_id == category_id)
        if question_type:
            stmt = stmt.where(QuestionBankItem.question_type == question_type)

        if chapter_id is not None:
            stmt = (
                stmt.join(
                    PaperReviewQuestion,
                    QuestionBankItem.first_source_question_id == PaperReviewQuestion.id,
                )
                .join(
                    PaperReviewQuestionKnowledgePoint,
                    and_(
                        PaperReviewQuestionKnowledgePoint.question_id == PaperReviewQuestion.id,
                        PaperReviewQuestionKnowledgePoint.status.in_(["confirmed", "suggested"]),
                    ),
                )
                .join(KnowledgePoint, KnowledgePoint.id == PaperReviewQuestionKnowledgePoint.knowledge_point_id)
                .where(KnowledgePoint.chapter_id == chapter_id)
            )

        if session_type == "paper":
            stmt = (
                stmt.join(
                    QuestionBankSourceLink,
                    and_(
                        QuestionBankSourceLink.bank_question_id == QuestionBankItem.id,
                        QuestionBankSourceLink.status == "active",
                    ),
                )
                .join(
                    PaperReviewQuestion,
                    QuestionBankSourceLink.source_question_id == PaperReviewQuestion.id,
                    isouter=True,
                )
            )
            if paper_id is not None:
                stmt = stmt.where(QuestionBankSourceLink.paper_id == paper_id)
            stmt = stmt.order_by(PaperReviewQuestion.sort_order.asc(), QuestionBankItem.id.asc())
        elif session_type == "wrong_book":
            stmt = stmt.join(
                WrongBookItem,
                and_(
                    WrongBookItem.bank_question_id == QuestionBankItem.id,
                    WrongBookItem.user_id == user_id,
                    WrongBookItem.mastered.is_(False),
                ),
            ).order_by(
                WrongBookItem.wrong_count.desc(),
                desc(WrongBookItem.last_wrong_at),
                QuestionBankItem.id.asc(),
            )
        else:
            stmt = stmt.order_by(QuestionBankItem.updated_at.desc(), QuestionBankItem.id.desc())

        return list(self.session.scalars(stmt.distinct()))

    def get_subject(self, subject_id: int | None) -> Subject | None:
        if subject_id is None:
            return None
        return self.session.get(Subject, subject_id)

    def get_category(self, category_id: int | None) -> SubjectCategory | None:
        if category_id is None:
            return None
        return self.session.get(SubjectCategory, category_id)

    def get_chapter(self, chapter_id: int | None) -> Chapter | None:
        if chapter_id is None:
            return None
        return self.session.get(Chapter, chapter_id)

    def get_paper(self, paper_id: int | None) -> ExamPaper | None:
        if paper_id is None:
            return None
        return self.session.get(ExamPaper, paper_id)

    def list_question_sources(
        self,
        bank_question_ids: list[int],
    ) -> list[tuple[QuestionBankSourceLink, PaperReviewQuestion | None, ExamPaper | None]]:
        if not bank_question_ids:
            return []
        stmt = (
            select(QuestionBankSourceLink, PaperReviewQuestion, ExamPaper)
            .join(PaperReviewQuestion, QuestionBankSourceLink.source_question_id == PaperReviewQuestion.id, isouter=True)
            .join(ExamPaper, QuestionBankSourceLink.paper_id == ExamPaper.id, isouter=True)
            .where(
                QuestionBankSourceLink.bank_question_id.in_(bank_question_ids),
                QuestionBankSourceLink.status == "active",
            )
            .order_by(
                QuestionBankSourceLink.bank_question_id.asc(),
                PaperReviewQuestion.sort_order.asc(),
                QuestionBankSourceLink.id.asc(),
            )
        )
        return list(self.session.execute(stmt).all())

    def list_review_question_tags(
        self,
        review_question_ids: list[int],
    ) -> list[tuple[PaperReviewQuestionKnowledgePoint, KnowledgePoint]]:
        if not review_question_ids:
            return []
        stmt = (
            select(PaperReviewQuestionKnowledgePoint, KnowledgePoint)
            .join(KnowledgePoint, KnowledgePoint.id == PaperReviewQuestionKnowledgePoint.knowledge_point_id)
            .where(
                PaperReviewQuestionKnowledgePoint.question_id.in_(review_question_ids),
                PaperReviewQuestionKnowledgePoint.status.in_(["confirmed", "suggested"]),
            )
            .order_by(
                PaperReviewQuestionKnowledgePoint.question_id.asc(),
                PaperReviewQuestionKnowledgePoint.status.asc(),
                PaperReviewQuestionKnowledgePoint.rank.asc(),
                PaperReviewQuestionKnowledgePoint.id.asc(),
            )
        )
        return list(self.session.execute(stmt).all())

    def list_questions_by_knowledge_points(
        self,
        knowledge_point_ids: list[int],
        *,
        exclude_bank_question_ids: list[int] | None = None,
        subject_id: int | None = None,
        limit: int = 20,
    ) -> list[QuestionBankItem]:
        if not knowledge_point_ids:
            return []
        stmt = (
            select(QuestionBankItem)
            .join(PaperReviewQuestion, QuestionBankItem.first_source_question_id == PaperReviewQuestion.id)
            .join(
                PaperReviewQuestionKnowledgePoint,
                and_(
                    PaperReviewQuestionKnowledgePoint.question_id == PaperReviewQuestion.id,
                    PaperReviewQuestionKnowledgePoint.status.in_(["confirmed", "suggested"]),
                ),
            )
            .where(
                QuestionBankItem.status == "active",
                QuestionBankItem.node_role != "group",
                PaperReviewQuestionKnowledgePoint.knowledge_point_id.in_(knowledge_point_ids),
            )
        )
        if exclude_bank_question_ids:
            stmt = stmt.where(~QuestionBankItem.id.in_(exclude_bank_question_ids))
        if subject_id is not None:
            stmt = stmt.where(QuestionBankItem.subject_id == subject_id)
        stmt = stmt.order_by(QuestionBankItem.updated_at.desc(), QuestionBankItem.id.desc()).limit(limit * 4)
        return list(self.session.scalars(stmt.distinct()))

    def count_answered_items(self, session_id: int) -> int:
        stmt = select(func.count(PracticeAnswer.id)).where(
            PracticeAnswer.session_id == session_id,
            and_(PracticeAnswer.learner_answer.is_not(None), PracticeAnswer.learner_answer != ""),
        )
        return int(self.session.scalar(stmt) or 0)

    def count_correct_items(self, session_id: int) -> int:
        stmt = select(func.count(PracticeAnswer.id)).where(
            PracticeAnswer.session_id == session_id,
            PracticeAnswer.is_correct.is_(True),
        )
        return int(self.session.scalar(stmt) or 0)
