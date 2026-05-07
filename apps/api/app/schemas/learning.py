from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class LearningHomeResponse(BaseModel):
    learner_name: str | None = None
    target_exam: str | None = None
    active_subject: str | None = None
    total_sessions: int
    wrong_book_count: int
    favorite_count: int
    weakest_points: list[str]


class PracticeSessionResponse(ORMModel):
    id: int
    learner_id: int
    session_type: str
    subject_id: int | None = None
    practice_set_id: int | None = None
    mock_exam_id: int | None = None
    status: str
    started_at: datetime | None = None
    submitted_at: datetime | None = None
    score: int | None = None
    accuracy_rate: float | None = None
    duration_seconds: int | None = None


class StartPracticeRequest(BaseModel):
    practice_set_id: int


class PracticeAnswerSubmit(BaseModel):
    bank_question_id: int
    learner_answer: str | None = None
    spent_seconds: int | None = None


class SubmitPracticeRequest(BaseModel):
    answers: list[PracticeAnswerSubmit]
    duration_seconds: int | None = None


class WrongBookResponse(ORMModel):
    id: int
    learner_id: int
    bank_question_id: int
    source_session_id: int | None = None
    wrong_count: int
    mastered: bool


class MasteryResponse(ORMModel):
    id: int
    learner_id: int
    subject_id: int
    knowledge_point_id: int
    mastery_score: float
    answered_count: int
    correct_count: int
    snapshot_date: date
    knowledge_point_name: str | None = None
