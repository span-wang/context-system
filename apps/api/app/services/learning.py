from __future__ import annotations

from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import MasterySnapshot, PracticeAnswer, PracticeSession, WrongBookItem
from app.repositories.knowledge import KnowledgeRepository
from app.repositories.learning import LearningRepository
from app.schemas.learning import (
    LearningHomeResponse,
    MasteryResponse,
    PracticeSessionResponse,
    StartPracticeRequest,
    SubmitPracticeRequest,
    WrongBookResponse,
)
from app.schemas.question_bank import PracticeSetResponse


class PracticeSessionService:
    def __init__(self, session: Session) -> None:
        self.repository = LearningRepository(session)
        self.knowledge_repository = KnowledgeRepository(session)

    def get_home(self) -> LearningHomeResponse:
        learner = self.repository.get_first_learner()
        sessions = self.repository.list_sessions(learner.id if learner else None)
        wrong_items = self.repository.list_wrong_book_items(learner.id if learner else None)
        favorites = self.repository.list_favorites(learner.id if learner else None)
        mastery = self.repository.list_mastery(learner.id if learner else None)
        points = {point.id: point for point in self.knowledge_repository.list_knowledge_points()}
        weakest = [points[item.knowledge_point_id].name for item in mastery[-3:] if points.get(item.knowledge_point_id)]
        return LearningHomeResponse(
            learner_name=None if learner is None else "演示学员",
            target_exam=learner.target_exam if learner else None,
            active_subject=learner.preferred_subjects_json[0] if learner and learner.preferred_subjects_json else None,
            total_sessions=len(sessions),
            wrong_book_count=len(wrong_items),
            favorite_count=len(favorites),
            weakest_points=weakest,
        )

    def list_practice_sets(self) -> list[PracticeSetResponse]:
        return [PracticeSetResponse.model_validate(item) for item in self.repository.list_practice_sets()]

    def list_sessions(self) -> list[PracticeSessionResponse]:
        learner = self.repository.get_first_learner()
        return [
            PracticeSessionResponse.model_validate(item)
            for item in self.repository.list_sessions(learner.id if learner else None)
        ]

    def get_session(self, session_id: int) -> PracticeSessionResponse:
        session_item = self.repository.get_session(session_id)
        if session_item is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="练习记录不存在")
        return PracticeSessionResponse.model_validate(session_item)

    def start_practice(self, payload: StartPracticeRequest) -> PracticeSessionResponse:
        learner = self.repository.get_first_learner()
        if learner is None:
            raise HTTPException(status_code=422, detail="暂无学员档案")
        practice_set = self.repository.get_practice_set(payload.practice_set_id)
        if practice_set is None:
            raise HTTPException(status_code=404, detail="练习题包不存在")
        session_item = self.repository.create_session(
            PracticeSession(
                tenant_id=learner.tenant_id,
                learner_id=learner.id,
                session_type="practice_set",
                subject_id=practice_set.subject_id,
                practice_set_id=practice_set.id,
                mock_exam_id=None,
                status="started",
                started_at=datetime.utcnow(),
                created_by=learner.user_id,
                updated_by=learner.user_id,
            )
        )
        self.repository.session.commit()
        return PracticeSessionResponse.model_validate(session_item)

    def submit_practice(self, session_id: int, payload: SubmitPracticeRequest) -> PracticeSessionResponse:
        session_item = self.repository.get_session(session_id)
        if session_item is None:
            raise HTTPException(status_code=404, detail="练习记录不存在")
        if session_item.status == "submitted":
            return PracticeSessionResponse.model_validate(session_item)

        answer_map = {item.bank_question_id: item for item in payload.answers}
        set_questions = self.repository.list_practice_set_questions(session_item.practice_set_id or 0)
        correct_count = 0
        total_count = 0
        total_score = 0
        for set_question in set_questions:
            bank_question = self.repository.get_bank_question(set_question.bank_question_id)
            if bank_question is None:
                continue
            submitted = answer_map.get(bank_question.id)
            learner_answer = (submitted.learner_answer if submitted else "") or ""
            is_correct = _normalize_answer(learner_answer) == _normalize_answer(bank_question.canonical_answer or "")
            score = set_question.score or 1
            awarded = score if is_correct else 0
            total_count += 1
            correct_count += 1 if is_correct else 0
            total_score += awarded
            self.repository.create_answer(
                PracticeAnswer(
                    tenant_id=session_item.tenant_id,
                    session_id=session_item.id,
                    bank_question_id=bank_question.id,
                    learner_answer=learner_answer,
                    is_correct=is_correct,
                    score=awarded,
                    spent_seconds=submitted.spent_seconds if submitted else None,
                    knowledge_snapshot_json={"auto_checked": True},
                    created_by=session_item.created_by,
                    updated_by=session_item.updated_by,
                )
            )
            self._update_learning_snapshots(session_item, bank_question.id, is_correct)

        session_item.status = "submitted"
        session_item.submitted_at = datetime.utcnow()
        session_item.score = total_score
        session_item.accuracy_rate = round(correct_count / total_count, 2) if total_count else 0
        session_item.duration_seconds = payload.duration_seconds
        self.repository.session.commit()
        return PracticeSessionResponse.model_validate(session_item)

    def list_wrong_book(self) -> list[WrongBookResponse]:
        learner = self.repository.get_first_learner()
        return [
            WrongBookResponse.model_validate(item)
            for item in self.repository.list_wrong_book_items(learner.id if learner else None)
        ]

    def list_mastery(self) -> list[MasteryResponse]:
        learner = self.repository.get_first_learner()
        points = {point.id: point for point in self.knowledge_repository.list_knowledge_points()}
        rows = []
        for item in self.repository.list_mastery(learner.id if learner else None):
            rows.append(
                MasteryResponse.model_validate(
                    {
                        **item.__dict__,
                        "knowledge_point_name": points.get(item.knowledge_point_id).name if points.get(item.knowledge_point_id) else None,
                    }
                )
            )
        return rows

    def _update_learning_snapshots(self, session_item: PracticeSession, bank_question_id: int, is_correct: bool) -> None:
        learner_id = session_item.learner_id
        if not is_correct:
            wrong_item = self.repository.get_wrong_book_item(learner_id, bank_question_id)
            if wrong_item is None:
                wrong_item = self.repository.create_wrong_book_item(
                    WrongBookItem(
                        tenant_id=session_item.tenant_id,
                        learner_id=learner_id,
                        bank_question_id=bank_question_id,
                        source_session_id=session_item.id,
                        wrong_count=0,
                        mastered=False,
                        created_by=session_item.created_by,
                        updated_by=session_item.updated_by,
                    )
                )
            wrong_item.wrong_count += 1
            wrong_item.last_wrong_at = datetime.utcnow()
            wrong_item.mastered = False

        subject_id = session_item.subject_id
        if subject_id is None:
            return
        for point_id in self.repository.list_bank_question_knowledge_points(bank_question_id):
            mastery = self.repository.get_mastery_snapshot(learner_id, subject_id, point_id)
            if mastery is None:
                mastery = self.repository.create_mastery_snapshot(
                    MasterySnapshot(
                        tenant_id=session_item.tenant_id,
                        learner_id=learner_id,
                        subject_id=subject_id,
                        knowledge_point_id=point_id,
                        mastery_score=0,
                        answered_count=0,
                        correct_count=0,
                        snapshot_date=date.today(),
                        created_by=session_item.created_by,
                        updated_by=session_item.updated_by,
                    )
                )
            mastery.answered_count += 1
            mastery.correct_count += 1 if is_correct else 0
            mastery.mastery_score = round(mastery.correct_count / mastery.answered_count, 2)
            mastery.snapshot_date = date.today()


def _normalize_answer(value: str) -> str:
    return "".join(value.upper().split())
