from __future__ import annotations

from sqlalchemy import select

from app.models import (
    Favorite,
    KnowledgePoint,
    LearnerProfile,
    MasterySnapshot,
    PracticeAnswer,
    PracticeSession,
    PracticeSet,
    PracticeSetQuestion,
    QuestionBankItem,
    QuestionKnowledgeLink,
    QuestionSourceLink,
    WrongBookItem,
)
from app.repositories.base import Repository


class LearningRepository(Repository):
    def get_first_learner(self) -> LearnerProfile | None:
        return self.session.scalar(select(LearnerProfile).order_by(LearnerProfile.id.asc()))

    def list_practice_sets(self) -> list[PracticeSet]:
        return list(self.session.scalars(select(PracticeSet).order_by(PracticeSet.id.asc())))

    def list_sessions(self, learner_id: int | None = None) -> list[PracticeSession]:
        stmt = select(PracticeSession)
        if learner_id is not None:
            stmt = stmt.where(PracticeSession.learner_id == learner_id)
        stmt = stmt.order_by(PracticeSession.id.desc())
        return list(self.session.scalars(stmt))

    def get_session(self, session_id: int) -> PracticeSession | None:
        return self.session.get(PracticeSession, session_id)

    def list_answers(self, session_id: int) -> list[PracticeAnswer]:
        stmt = select(PracticeAnswer).where(PracticeAnswer.session_id == session_id).order_by(PracticeAnswer.id.asc())
        return list(self.session.scalars(stmt))

    def list_wrong_book_items(self, learner_id: int | None = None) -> list[WrongBookItem]:
        stmt = select(WrongBookItem)
        if learner_id is not None:
            stmt = stmt.where(WrongBookItem.learner_id == learner_id)
        stmt = stmt.order_by(WrongBookItem.wrong_count.desc(), WrongBookItem.id.asc())
        return list(self.session.scalars(stmt))

    def list_favorites(self, learner_id: int | None = None) -> list[Favorite]:
        stmt = select(Favorite)
        if learner_id is not None:
            stmt = stmt.where(Favorite.learner_id == learner_id)
        stmt = stmt.order_by(Favorite.id.asc())
        return list(self.session.scalars(stmt))

    def list_mastery(self, learner_id: int | None = None) -> list[MasterySnapshot]:
        stmt = select(MasterySnapshot)
        if learner_id is not None:
            stmt = stmt.where(MasterySnapshot.learner_id == learner_id)
        stmt = stmt.order_by(MasterySnapshot.mastery_score.desc())
        return list(self.session.scalars(stmt))

    def get_practice_set(self, practice_set_id: int) -> PracticeSet | None:
        return self.session.get(PracticeSet, practice_set_id)

    def list_practice_set_questions(self, practice_set_id: int) -> list[PracticeSetQuestion]:
        stmt = select(PracticeSetQuestion).where(PracticeSetQuestion.practice_set_id == practice_set_id)
        stmt = stmt.order_by(PracticeSetQuestion.sort_order.asc())
        return list(self.session.scalars(stmt))

    def get_bank_question(self, question_id: int) -> QuestionBankItem | None:
        return self.session.get(QuestionBankItem, question_id)

    def list_bank_questions_by_ids(self, question_ids: list[int]) -> list[QuestionBankItem]:
        if not question_ids:
            return []
        stmt = select(QuestionBankItem).where(QuestionBankItem.id.in_(question_ids)).order_by(QuestionBankItem.id.asc())
        return list(self.session.scalars(stmt))

    def list_bank_question_knowledge_points(self, bank_question_id: int) -> list[int]:
        stmt = (
            select(QuestionKnowledgeLink.knowledge_point_id)
            .join(QuestionSourceLink, QuestionSourceLink.exam_question_id == QuestionKnowledgeLink.question_id)
            .where(QuestionSourceLink.bank_question_id == bank_question_id)
        )
        return list(dict.fromkeys(self.session.scalars(stmt)))

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

    def create_session(self, item: PracticeSession) -> PracticeSession:
        self.session.add(item)
        self.session.flush()
        return item

    def create_answer(self, item: PracticeAnswer) -> PracticeAnswer:
        self.session.add(item)
        self.session.flush()
        return item

    def get_wrong_book_item(self, learner_id: int, bank_question_id: int) -> WrongBookItem | None:
        stmt = select(WrongBookItem).where(
            WrongBookItem.learner_id == learner_id,
            WrongBookItem.bank_question_id == bank_question_id,
        )
        return self.session.scalar(stmt)

    def create_wrong_book_item(self, item: WrongBookItem) -> WrongBookItem:
        self.session.add(item)
        self.session.flush()
        return item

    def get_mastery_snapshot(self, learner_id: int, subject_id: int, knowledge_point_id: int) -> MasterySnapshot | None:
        stmt = select(MasterySnapshot).where(
            MasterySnapshot.learner_id == learner_id,
            MasterySnapshot.subject_id == subject_id,
            MasterySnapshot.knowledge_point_id == knowledge_point_id,
        )
        return self.session.scalar(stmt)

    def create_mastery_snapshot(self, item: MasterySnapshot) -> MasterySnapshot:
        self.session.add(item)
        self.session.flush()
        return item
