from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from pydantic import Field

from app.schemas.common import ORMModel


class QuestionPatchRequest(BaseModel):
    question_no: str | None = None
    question_type: str | None = None
    stem_text: str | None = None
    options_json: list[str] | None = None
    answer_text: str | None = None
    analysis_text: str | None = None
    score: int | None = None
    difficulty_level: int | None = None
    review_status: str | None = None
    review_note: str | None = None


class QuestionBatchReviewRequest(BaseModel):
    question_ids: list[int] = Field(min_length=1)
    review_status: str
    review_note: str | None = None


class QuestionBatchReviewResponse(BaseModel):
    updated_count: int
    review_status: str
    question_ids: list[int]


class QuestionKnowledgeReviewRequest(BaseModel):
    link_ids: list[int] = Field(min_length=1)
    review_status: str
    primary_link_id: int | None = None


class QuestionKnowledgeReviewResponse(BaseModel):
    question_id: int
    updated_count: int
    review_status: str
    link_ids: list[int]
    primary_link_id: int | None = None


class QuestionRetagResponse(BaseModel):
    question_id: int
    created_links: int
    ai_created_links: int = 0
    total_links: int


class QuestionAiCompleteRequest(BaseModel):
    question_ids: list[int] = Field(min_length=1)


class QuestionAiCompleteResponse(BaseModel):
    requested_count: int
    updated_count: int
    unchanged_count: int
    failed_count: int
    question_ids: list[int]
    failed_question_ids: list[int]
    message: str


class QuestionAiReviewRequest(BaseModel):
    question_ids: list[int] = Field(min_length=1)


class QuestionAiReviewResponse(BaseModel):
    requested_count: int
    updated_count: int
    approved_count: int
    needs_revision_count: int
    rejected_count: int
    failed_count: int
    question_ids: list[int]
    failed_question_ids: list[int]
    message: str


class QuestionAiKnowledgeReviewRequest(BaseModel):
    link_ids: list[int] = Field(min_length=1)


class QuestionAiKnowledgeReviewResponse(BaseModel):
    question_id: int
    updated_count: int
    approved_count: int
    rejected_count: int
    link_ids: list[int]
    primary_link_id: int | None = None
    message: str


class QuestionAiProcessRequest(BaseModel):
    question_ids: list[int] = Field(min_length=1)


class QuestionAiProcessResponse(BaseModel):
    requested_count: int
    updated_count: int
    completed_count: int
    approved_count: int
    needs_revision_count: int
    rejected_count: int
    tagged_question_count: int
    created_link_count: int
    failed_count: int
    question_ids: list[int]
    failed_question_ids: list[int]
    message: str


class QuestionSummary(ORMModel):
    id: int
    paper_id: int
    subject_id: int
    section_id: int | None = None
    question_no: str
    question_uid: str
    question_type: str
    stem_text: str
    answer_text: str | None = None
    score: int | None = None
    difficulty_level: int | None = None
    parse_status: str
    review_status: str
    review_note: str | None = None
    paper_name: str | None = None
    source_label: str | None = None
    source_year: int | None = None
    source_region: str | None = None


class QuestionKnowledgeLinkResponse(ORMModel):
    id: int
    knowledge_point_id: int
    question_layer: str
    link_type: str
    confidence_score: float | None = None
    evidence_text: str | None = None
    tag_source: str | None = None
    is_primary: bool
    review_status: str
    reviewed_at: datetime | None = None
    knowledge_point_name: str | None = None


class QuestionDetailResponse(QuestionSummary):
    options_json: list[str] | None = None
    analysis_text: str | None = None
    source_page_from: int | None = None
    source_page_to: int | None = None
    quality_score: float | None = None
    links: list[QuestionKnowledgeLinkResponse]
