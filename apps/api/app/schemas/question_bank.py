from __future__ import annotations

from pydantic import BaseModel

from app.schemas.common import ORMModel


class StandardizeQuestionsRequest(BaseModel):
    paper_id: int | None = None
    publish: bool = True


class StandardizeQuestionsResponse(BaseModel):
    created: int
    linked: int
    skipped: int


class GeneratePracticeSetRequest(BaseModel):
    subject_id: int | None = None
    title: str | None = None
    question_limit: int = 10
    set_type: str = "auto"


class GenerateMockExamRequest(BaseModel):
    subject_id: int | None = None
    title: str | None = None
    question_limit: int = 20
    duration_minutes: int = 45


class QuestionBankItemResponse(ORMModel):
    id: int
    subject_id: int
    canonical_stem: str
    canonical_options_json: list[str] | None = None
    canonical_answer: str | None = None
    canonical_analysis: str | None = None
    question_type: str
    difficulty_level: int | None = None
    quality_score: float | None = None
    source_count: int
    status: str


class PracticeSetResponse(ORMModel):
    id: int
    subject_id: int
    set_type: str
    title: str
    description: str | None = None
    source_report_id: int | None = None
    difficulty_policy: str | None = None
    question_count: int
    status: str


class MockExamResponse(ORMModel):
    id: int
    subject_id: int
    title: str
    exam_mode: str
    duration_minutes: int | None = None
    total_score: int | None = None
    status: str
