from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


PracticeSessionType = Literal["chapter", "random", "paper", "wrong_book"]
PracticeAnswerMode = Literal["memorize", "exam"]
PracticeWrongReasonTag = Literal[
    "concept_unclear",
    "memory_unstable",
    "misread_question",
    "calculation_error",
    "careless",
    "method_unfamiliar",
]


class PracticeQuestionKnowledgePointResponse(BaseModel):
    id: int
    name: str
    path: str
    relation_type: str
    status: str


class PracticeQuestionSnapshotResponse(BaseModel):
    bank_question_id: int | None = None
    question_uid: str
    node_role: str
    question_type: str
    group_stem: str | None = None
    material_text: str | None = None
    stem_text: str
    options_json: list[str] | None = None
    difficulty_level: int | None = None
    source_paper_name: str | None = None
    source_question_no: str | None = None
    knowledge_points: list[PracticeQuestionKnowledgePointResponse] = Field(default_factory=list)
    answer_text: str | None = None
    analysis_text: str | None = None


class PracticeSessionItemResponse(ORMModel):
    id: int
    sort_order: int
    score: int
    question: PracticeQuestionSnapshotResponse
    user_answer: str | None = None
    is_answered: bool = False
    is_correct: bool | None = None
    marked: bool = False
    spent_seconds: int | None = None
    show_result: bool = False


class PracticeSessionSummaryResponse(ORMModel):
    id: int
    title: str
    session_type: PracticeSessionType
    answer_mode: PracticeAnswerMode
    status: str
    total_count: int
    answered_count: int
    correct_count: int
    accuracy_rate: float | None = None
    created_at: datetime
    started_at: datetime | None = None
    submitted_at: datetime | None = None


class PracticeSessionDetailResponse(PracticeSessionSummaryResponse):
    subject_id: int | None = None
    category_id: int | None = None
    chapter_id: int | None = None
    paper_id: int | None = None
    duration_seconds: int | None = None
    can_show_solutions: bool = False
    can_submit: bool = False
    incomplete_count: int = 0
    today_review_count: int = 0
    retry_wrong_count: int = 0
    similar_practice_available: bool = False
    weak_points: list["MasterySnapshotResponse"] = Field(default_factory=list)
    items: list[PracticeSessionItemResponse] = Field(default_factory=list)


class PracticeSessionCreateRequest(BaseModel):
    session_type: PracticeSessionType
    answer_mode: PracticeAnswerMode
    subject_id: int | None = None
    category_id: int | None = None
    chapter_id: int | None = None
    paper_id: int | None = None
    question_type: str | None = None
    question_count: int = Field(default=20, ge=1, le=100)


class PracticeAnswerSubmitRequest(BaseModel):
    item_id: int
    answer: str | None = None
    spent_seconds: int | None = Field(default=None, ge=0, le=86400)
    marked: bool = False


class PracticeAnswerReflectionRequest(BaseModel):
    item_id: int
    wrong_reason_tags: list[PracticeWrongReasonTag] = Field(default_factory=list, max_length=4)
    reflection_note: str | None = None


class PracticeDerivedSessionRequest(BaseModel):
    answer_mode: PracticeAnswerMode = "memorize"
    question_count: int = Field(default=10, ge=1, le=50)


class MasterySnapshotResponse(ORMModel):
    knowledge_point_id: int
    name: str
    path: str
    chapter_id: int | None = None
    mastery_score: float
    answered_count: int
    correct_count: int
    snapshot_date: date | None = None
    last_practiced_at: datetime | None = None


class ReviewDueItemResponse(ORMModel):
    id: int
    bank_question_id: int | None = None
    question_type: str
    stem_text: str
    source_paper_name: str | None = None
    knowledge_points: list[PracticeQuestionKnowledgePointResponse] = Field(default_factory=list)
    wrong_count: int
    correct_streak: int
    due_at: datetime
    due_reason: str


class PracticeWrongReasonCountResponse(BaseModel):
    reason_code: PracticeWrongReasonTag
    reason_label: str
    count: int


class PracticeResultItemResponse(ORMModel):
    id: int
    sort_order: int
    score: int
    question: PracticeQuestionSnapshotResponse
    user_answer: str | None = None
    is_correct: bool | None = None
    marked: bool = False
    spent_seconds: int | None = None
    wrong_reason_tags: list[PracticeWrongReasonTag] = Field(default_factory=list)
    reflection_note: str | None = None


class PracticeResultResponse(ORMModel):
    id: int
    title: str
    session_type: PracticeSessionType
    answer_mode: PracticeAnswerMode
    total_count: int
    correct_count: int
    wrong_count: int
    accuracy_rate: float | None = None
    duration_seconds: int | None = None
    submitted_at: datetime | None = None
    today_review_count: int = 0
    retry_wrong_count: int = 0
    similar_practice_available: bool = False
    weak_points: list[MasterySnapshotResponse] = Field(default_factory=list)
    wrong_reason_counts: list[PracticeWrongReasonCountResponse] = Field(default_factory=list)
    review_suggestions: list[str] = Field(default_factory=list)
    items: list[PracticeResultItemResponse] = Field(default_factory=list)


class DailyPlanTaskResponse(BaseModel):
    task_id: str
    task_type: str
    title: str
    description: str
    priority: str
    question_count: int
    action_type: str | None = None
    session_create_payload: PracticeSessionCreateRequest | None = None
    derived_session_payload: PracticeDerivedSessionRequest | None = None


class DailyPlanResponse(BaseModel):
    headline: str
    summary: str
    review_today_count: int = 0
    weak_points: list[MasterySnapshotResponse] = Field(default_factory=list)
    tasks: list[DailyPlanTaskResponse] = Field(default_factory=list)


class WrongBookItemResponse(ORMModel):
    id: int
    bank_question_id: int | None = None
    question_type: str
    stem_text: str
    source_paper_name: str | None = None
    knowledge_points: list[PracticeQuestionKnowledgePointResponse] = Field(default_factory=list)
    wrong_count: int
    correct_streak: int
    mastered: bool
    last_wrong_at: datetime | None = None
    last_practiced_at: datetime | None = None
    due_at: datetime | None = None
    due_reason: str | None = None


PracticeSessionDetailResponse.model_rebuild()
