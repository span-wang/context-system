from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


QuestionBankStatus = Literal["draft", "active", "inactive", "archived"]
QuestionBankExportSolutionMode = Literal["inline", "appendix"]
QuestionBankNodeRole = Literal["standalone", "group", "subquestion"]


class QuestionBankKnowledgePointResponse(BaseModel):
    id: int
    name: str
    path: str
    relation_type: str
    status: str


class QuestionBankSourceResponse(BaseModel):
    id: int
    source_type: str
    source_question_id: int
    paper_id: int | None = None
    paper_name: str | None = None
    section_id: int | None = None
    question_no: str | None = None
    status: str
    created_at: datetime


class QuestionBankItemResponse(ORMModel):
    id: int
    subject_id: int | None = None
    subject_name: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    parent_question_id: int | None = None
    question_no: str | None = None
    question_uid: str
    content_fingerprint: str
    node_role: QuestionBankNodeRole = "standalone"
    question_type: str
    group_stem: str | None = None
    material_text: str | None = None
    stem_text: str
    options_json: list[str] | None = None
    answer_text: str | None = None
    analysis_text: str | None = None
    difficulty_level: int | None = None
    quality_score: float | None = None
    subquestion_count: int = 0
    status: str
    source_count: int
    first_source_question_id: int | None = None
    first_source_paper_name: str | None = None
    created_at: datetime
    updated_at: datetime
    knowledge_points: list[QuestionBankKnowledgePointResponse] = Field(default_factory=list)
    subquestions: list["QuestionBankItemResponse"] = Field(default_factory=list)


class QuestionBankListResponse(BaseModel):
    total: int
    items: list[QuestionBankItemResponse]
    status_counts: dict[str, int] = Field(default_factory=dict)


class QuestionBankExportPaperOptionResponse(BaseModel):
    paper_id: int
    paper_name: str
    subject_name: str | None = None
    category_name: str | None = None
    question_count: int


class QuestionBankPaperExportRequest(BaseModel):
    paper_id: int
    solution_mode: QuestionBankExportSolutionMode = "inline"
    subject_id: int | None = None
    category_id: int | None = None
    status: QuestionBankStatus | None = None
    question_type: str | None = None
    keyword: str | None = None


class QuestionBankItemUpdateRequest(BaseModel):
    status: QuestionBankStatus | None = None


class QuestionBankSyncResponse(BaseModel):
    bank_question_id: int
    source_link_id: int
    created: bool
    linked: bool
    status: str
    message: str


class QuestionBankDeleteResponse(BaseModel):
    id: int
    question_uid: str
    deleted: bool
    removed_source_link_count: int = 0
    message: str


class QuestionBankAnalysisSummaryResponse(BaseModel):
    paper_count: int = 0
    bank_question_count: int = 0
    source_question_count: int = 0
    tagged_source_question_count: int = 0
    point_count: int = 0
    chapter_count: int = 0
    year_count: int = 0
    primary_coverage_rate: float = 0
    top_point_concentration_rate: float = 0


class QuestionBankAnalysisYearOverviewResponse(BaseModel):
    year: int
    paper_count: int = 0
    source_question_count: int = 0
    tagged_source_question_count: int = 0


class QuestionBankAnalysisDistributionItemResponse(BaseModel):
    key: str
    name: str
    path: str | None = None
    total_frequency: int = 0
    paper_count: int = 0
    yearly_frequency: list[int] = Field(default_factory=list)
    share: float = 0
    last_frequency: int = 0
    recent_average: float = 0
    slope: float = 0
    trend_label: str = "stable"
    prediction_frequency: int = 0
    confidence: float = 0
    appearance_year_count: int = 0


class QuestionBankAnalysisPointItemResponse(QuestionBankAnalysisDistributionItemResponse):
    knowledge_point_id: int | None = None
    chapter_name: str | None = None


class QuestionBankAnalysisChapterItemResponse(QuestionBankAnalysisDistributionItemResponse):
    chapter_key: str


class QuestionBankAnalysisPredictionItemResponse(BaseModel):
    key: str
    name: str
    prediction_frequency: int = 0
    confidence: float = 0
    trend_label: str = "stable"
    evidence: str


class QuestionBankAnalysisReportResponse(BaseModel):
    overview: str
    point_insight: str
    chapter_insight: str
    forecast: str
    disclaimer: str


class QuestionBankKnowledgeAnalysisResponse(BaseModel):
    data_scope: str
    subject_id: int | None = None
    subject_name: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    start_year: int | None = None
    end_year: int | None = None
    years: list[int] = Field(default_factory=list)
    prediction_year: int | None = None
    summary: QuestionBankAnalysisSummaryResponse = Field(default_factory=QuestionBankAnalysisSummaryResponse)
    yearly_overview: list[QuestionBankAnalysisYearOverviewResponse] = Field(default_factory=list)
    point_distribution: list[QuestionBankAnalysisPointItemResponse] = Field(default_factory=list)
    chapter_distribution: list[QuestionBankAnalysisChapterItemResponse] = Field(default_factory=list)
    top_predicted_points: list[QuestionBankAnalysisPredictionItemResponse] = Field(default_factory=list)
    top_predicted_chapters: list[QuestionBankAnalysisPredictionItemResponse] = Field(default_factory=list)
    report: QuestionBankAnalysisReportResponse


QuestionBankItemResponse.model_rebuild()
