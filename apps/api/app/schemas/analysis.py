from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class DashboardMetric(BaseModel):
    key: str
    label: str
    value: str
    trend: str | None = None


class DashboardFocusItem(BaseModel):
    knowledge_point_id: int
    knowledge_point_name: str
    frequency: int
    paper_coverage: int
    hot_score: float


class DashboardResponse(BaseModel):
    metrics: list[DashboardMetric]
    focus_points: list[DashboardFocusItem]
    pending_reviews: int
    latest_report_name: str | None = None


class AnalysisFilterOption(BaseModel):
    value: str
    label: str


class AnalysisMetric(BaseModel):
    key: str
    label: str
    value: str
    helper: str | None = None


class FrequencyResponse(BaseModel):
    knowledge_point_id: int
    knowledge_point_name: str
    question_count: int
    paper_count: int
    hot_score: float


class TrendResponse(BaseModel):
    label: str
    year: int | None = None
    question_count: int


class AnalysisYearSummary(BaseModel):
    year: int | None = None
    label: str
    paper_count: int
    question_count: int
    mapped_question_count: int
    total_score: float


class AnalysisTypeBreakdown(BaseModel):
    question_type: str
    question_type_label: str
    count: int
    score: float
    count_share: float
    score_share: float


class AnalysisPointYearStat(BaseModel):
    year: int | None = None
    label: str
    frequency: int
    paper_count: int
    score: float
    score_share: float


class AnalysisPointRow(BaseModel):
    knowledge_point_id: int
    knowledge_point_name: str
    chapter_id: int | None = None
    chapter_name: str | None = None
    chapter_path: str | None = None
    category_name: str | None = None
    frequency: int
    paper_coverage: int
    total_score: float
    score_share: float
    avg_score: float
    continuous_years: int
    last_seen_year: int | None = None
    dominant_question_type: str | None = None
    dominant_question_type_label: str | None = None
    dominant_question_type_share: float
    hot_score: float
    importance_level: str
    type_breakdown: list[AnalysisTypeBreakdown]
    yearly_stats: list[AnalysisPointYearStat]


class AnalysisChapterYearStat(BaseModel):
    year: int | None = None
    label: str
    frequency: int
    score: float
    score_share: float


class AnalysisChapterRow(BaseModel):
    chapter_id: int
    chapter_name: str
    chapter_path: str
    point_count: int
    frequency: int
    paper_coverage: int
    total_score: float
    score_share: float
    yearly_stats: list[AnalysisChapterYearStat]


class AnalysisInsight(BaseModel):
    title: str
    description: str


class KnowledgeAnalysisResponse(BaseModel):
    data_as_of: date
    coverage_rate: float
    summary_metrics: list[AnalysisMetric]
    available_years: list[int]
    available_question_types: list[AnalysisFilterOption]
    available_paper_types: list[str]
    available_regions: list[str]
    years: list[AnalysisYearSummary]
    points: list[AnalysisPointRow]
    chapters: list[AnalysisChapterRow]
    insights: list[AnalysisInsight]


class GenerateReportRequest(BaseModel):
    subject_id: int | None = None
    report_type: str = "hot_knowledge"
    report_name: str | None = None


class ReportResponse(ORMModel):
    id: int
    subject_id: int | None = None
    report_type: str
    report_name: str
    snapshot_date: date | None = None
    version_no: int
    status: str
    report_json: dict | None = None
    created_at: datetime


class AnalysisJobResponse(ORMModel):
    id: int
    job_type: str
    subject_id: int | None = None
    scope_type: str
    scope_config_json: dict | None = None
    status: str
    progress: int
    result_summary_json: dict | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
