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
