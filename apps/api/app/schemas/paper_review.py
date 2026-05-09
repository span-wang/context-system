from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.papers import AnalysisJobResponse
from app.schemas.papers import PaperSectionResponse


ReviewStatus = Literal["pending", "approved", "needs_revision", "rejected"]
KnowledgePointTagStatus = Literal["suggested", "confirmed", "rejected"]
KnowledgePointRelationType = Literal["primary", "secondary"]


class PaperReviewQuestionKnowledgePointResponse(BaseModel):
    id: int
    question_id: int
    knowledge_point_id: int
    name: str
    path: str
    chapter_id: int | None = None
    category_id: int | None = None
    status: KnowledgePointTagStatus
    relation_type: KnowledgePointRelationType
    source: str
    confidence: float | None = None
    reason: str | None = None
    rank: int = 0


class PaperReviewQuestionResponse(ORMModel):
    id: int
    paper_id: int
    section_id: int | None = None
    question_uid: str
    content_fingerprint: str
    sort_order: int
    question_no: str
    question_type: str
    source_section_name: str
    source_raw_text: str
    stem_text: str
    options_json: list[str] | None = None
    answer_text: str | None = None
    analysis_text: str | None = None
    difficulty_level: int | None = None
    quality_score: float | None = None
    subquestion_count: int = 0
    quality_issues_json: list[str] | None = None
    parse_status: str
    review_status: str
    review_note: str | None = None
    ai_review_status: str | None = None
    ai_review_note: str | None = None
    ai_standardization_note: str | None = None
    last_ai_standardized_at: datetime | None = None
    last_ai_reviewed_at: datetime | None = None
    reviewed_by: int | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    suggested_knowledge_points: list[PaperReviewQuestionKnowledgePointResponse] = Field(default_factory=list)
    confirmed_knowledge_points: list[PaperReviewQuestionKnowledgePointResponse] = Field(default_factory=list)


class PaperReviewSummaryResponse(BaseModel):
    total_questions: int
    pending_count: int = 0
    approved_count: int = 0
    needs_revision_count: int = 0
    rejected_count: int = 0
    ai_flagged_count: int = 0
    ai_reviewed_count: int = 0
    missing_solution_count: int = 0


class PaperReviewPaperResponse(BaseModel):
    id: int
    paper_name: str
    subject_name: str | None = None
    category: str | None = None
    status: str
    review_status: str
    total_question_count: int = 0
    question_review_count: int = 0


class PaperReviewWorkspaceResponse(BaseModel):
    paper: PaperReviewPaperResponse
    sections: list[PaperSectionResponse] = Field(default_factory=list)
    summary: PaperReviewSummaryResponse
    questions: list[PaperReviewQuestionResponse] = Field(default_factory=list)


class PaperReviewQuestionUpdateRequest(BaseModel):
    question_type: str | None = None
    stem_text: str | None = None
    options_json: list[str] | None = None
    answer_text: str | None = None
    analysis_text: str | None = None
    review_status: ReviewStatus | None = None
    review_note: str | None = None


class PaperReviewQuestionKnowledgePointUpsertItem(BaseModel):
    knowledge_point_id: int
    relation_type: KnowledgePointRelationType = "secondary"
    source: str = "manual"
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str | None = None
    rank: int = Field(default=0, ge=0)


class PaperReviewQuestionKnowledgePointUpdateRequest(BaseModel):
    suggested: list[PaperReviewQuestionKnowledgePointUpsertItem] = Field(default_factory=list)
    confirmed: list[PaperReviewQuestionKnowledgePointUpsertItem] = Field(default_factory=list)


class PaperReviewRebuildResponse(BaseModel):
    paper_id: int
    imported_count: int
    replaced_count: int
    section_count: int
    message: str


class PaperReviewAutoTagResponse(BaseModel):
    paper_id: int
    status: str = "pending"
    progress: int = 0
    requested_count: int
    updated_count: int
    failed_count: int
    skipped_count: int = 0
    message: str


class PaperReviewAutoTagJobResponse(ORMModel):
    job_id: int
    paper_id: int
    status: str
    progress: int


class PaperReviewAIActionResponse(BaseModel):
    message: str
    changed: bool = False
    used_ai: bool = False
    question: PaperReviewQuestionResponse
