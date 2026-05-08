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
    PracticeMode,
    PracticeAnswerResultResponse,
    PracticeSessionDetailResponse,
    PracticeSessionResponse,
    StartPracticeRequest,
    SubmitPracticeRequest,
    WrongBookResponse,
)
from app.schemas.question_bank import PracticeSetQuestionResponse, PracticeSetResponse
from app.models.practice import PracticeSetQuestion

PRACTICE_MODE_TO_SESSION_TYPE: dict[PracticeMode, str] = {
    "instant_feedback": "practice_set_instant_feedback",
    "deferred_feedback": "practice_set_deferred_feedback",
}


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
        return [self._build_session_response(item) for item in self.repository.list_sessions(learner.id if learner else None)]

    def get_session(self, session_id: int) -> PracticeSessionResponse:
        session_item = self.repository.get_session(session_id)
        if session_item is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="练习记录不存在")
        return self._build_session_response(session_item)

    def get_session_detail(self, session_id: int) -> PracticeSessionDetailResponse:
        session_item = self.repository.get_session(session_id)
        if session_item is None:
            raise HTTPException(status_code=404, detail="练习记录不存在")
        practice_set = self.repository.get_practice_set(session_item.practice_set_id or 0) if session_item.practice_set_id else None
        set_questions = self.repository.list_practice_set_questions(session_item.practice_set_id or 0) if session_item.practice_set_id else []
        question_rows = self._build_practice_question_rows(set_questions)
        answers = self.repository.list_answers(session_id)
        answers_by_bank_id = {answer.bank_question_id: answer for answer in answers}
        answer_rows = [
            PracticeAnswerResultResponse.model_validate(
                {
                    "bank_question_id": question.bank_question_id,
                    "learner_answer": answers_by_bank_id.get(question.bank_question_id).learner_answer if answers_by_bank_id.get(question.bank_question_id) else None,
                    "correct_answer": question.answer_text,
                    "is_correct": answers_by_bank_id.get(question.bank_question_id).is_correct if answers_by_bank_id.get(question.bank_question_id) else None,
                    "score": answers_by_bank_id.get(question.bank_question_id).score if answers_by_bank_id.get(question.bank_question_id) else None,
                    "full_score": question.score,
                    "spent_seconds": answers_by_bank_id.get(question.bank_question_id).spent_seconds if answers_by_bank_id.get(question.bank_question_id) else None,
                    "analysis_text": question.analysis_text,
                }
            )
            for question in question_rows
        ]
        return PracticeSessionDetailResponse.model_validate(
            {
                **self._build_session_payload(session_item),
                "practice_set_title": practice_set.title if practice_set else None,
                "questions": question_rows,
                "answers": answer_rows,
            }
        )

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
                session_type=_session_type_for_mode(payload.practice_mode),
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
        return self._build_session_response(session_item)

    def submit_practice(self, session_id: int, payload: SubmitPracticeRequest) -> PracticeSessionResponse:
        session_item = self.repository.get_session(session_id)
        if session_item is None:
            raise HTTPException(status_code=404, detail="练习记录不存在")
        if session_item.status == "submitted":
            return self._build_session_response(session_item)

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
            is_correct = _answers_match(learner_answer, bank_question.canonical_answer or "", bank_question.question_type)
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
        return self._build_session_response(session_item)

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

    def _build_practice_question_rows(self, questions: list[PracticeSetQuestion]) -> list[PracticeSetQuestionResponse]:
        if not questions:
            return []
        bank_question_ids = [item.bank_question_id for item in questions]
        bank_questions = {item.id: item for item in self.repository.list_bank_questions_by_ids(bank_question_ids)}
        knowledge_map = self.repository.list_knowledge_points_by_bank_question_ids(bank_question_ids)
        rows: list[PracticeSetQuestionResponse] = []
        for row in questions:
            bank_question = bank_questions.get(row.bank_question_id)
            if bank_question is None:
                continue
            rows.append(
                PracticeSetQuestionResponse.model_validate(
                    {
                        "id": row.id,
                        "bank_question_id": row.bank_question_id,
                        "sort_order": row.sort_order,
                        "score": row.score,
                        "question_type": bank_question.question_type,
                        "stem_text": bank_question.canonical_stem,
                        "options_json": bank_question.canonical_options_json,
                        "answer_text": bank_question.canonical_answer,
                        "analysis_text": bank_question.canonical_analysis,
                        "difficulty_level": bank_question.difficulty_level,
                        "quality_score": bank_question.quality_score,
                        "source_count": bank_question.source_count,
                        "knowledge_point_names": [point.name for point in knowledge_map.get(bank_question.id, [])],
                    }
                )
            )
        rows.sort(key=lambda item: item.sort_order)
        return rows

    def _build_session_payload(self, session_item: PracticeSession) -> dict:
        return {
            **session_item.__dict__,
            "practice_mode": _practice_mode_from_session_type(session_item.session_type),
        }

    def _build_session_response(self, session_item: PracticeSession) -> PracticeSessionResponse:
        return PracticeSessionResponse.model_validate(self._build_session_payload(session_item))


def _normalize_answer(value: str) -> str:
    return "".join(value.upper().split())


def _practice_mode_from_session_type(session_type: str) -> PracticeMode:
    for practice_mode, mapped_session_type in PRACTICE_MODE_TO_SESSION_TYPE.items():
        if session_type == mapped_session_type:
            return practice_mode
    return "deferred_feedback"


def _session_type_for_mode(practice_mode: PracticeMode) -> str:
    return PRACTICE_MODE_TO_SESSION_TYPE.get(practice_mode, PRACTICE_MODE_TO_SESSION_TYPE["deferred_feedback"])


def _answers_match(learner_answer: str, correct_answer: str, question_type: str) -> bool:
    learner = _normalize_answer(learner_answer)
    correct = _normalize_answer(correct_answer)
    if question_type == "multiple_choice":
        return "".join(sorted(learner)) == "".join(sorted(correct))
    return learner == correct
