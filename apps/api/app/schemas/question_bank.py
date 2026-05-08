from __future__ import annotations

from pydantic import BaseModel

from app.schemas.common import ORMModel


class StandardizeQuestionsRequest(BaseModel):
    paper_id: int | None = None
    publish: bool = True
    use_ai: bool = True


class StandardizeQuestionsResponse(BaseModel):
    created: int
    linked: int
    unlinked: int = 0
    skipped: int
    normalized: int = 0
    ai_completed: int = 0
    tagged: int = 0
    ai_tagged: int = 0


class QuestionSourceSummaryResponse(ORMModel):
    id: int
    exam_question_id: int
    paper_id: int
    paper_name: str
    question_no: str
    source_label: str
    source_year: int | None = None
    source_region: str | None = None


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
    source_labels: list[str] = []
    sources: list[QuestionSourceSummaryResponse] = []


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


class PracticeSetQuestionResponse(BaseModel):
    id: int
    bank_question_id: int
    sort_order: int
    score: int | None = None
    question_type: str
    stem_text: str
    options_json: list[str] | None = None
    answer_text: str | None = None
    analysis_text: str | None = None
    difficulty_level: int | None = None
    quality_score: float | None = None
    source_count: int = 0
    knowledge_point_names: list[str] = []


class PracticeSetDetailResponse(PracticeSetResponse):
    questions: list[PracticeSetQuestionResponse] = []


class MockExamResponse(ORMModel):
    id: int
    subject_id: int
    title: str
    exam_mode: str
    duration_minutes: int | None = None
    total_score: int | None = None
    status: str
