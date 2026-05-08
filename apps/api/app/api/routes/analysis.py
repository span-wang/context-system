from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.deps import get_session, require_roles
from app.schemas.auth import CurrentUserResponse
from app.schemas.analysis import (
    AnalysisJobResponse,
    DashboardResponse,
    FrequencyResponse,
    GenerateReportRequest,
    KnowledgeAnalysisResponse,
    ReportResponse,
    TrendResponse,
)
from app.services.audit import AuditService
from app.services.analysis import FrequencyAnalysisService


router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(session: Session = Depends(get_session)) -> DashboardResponse:
    return FrequencyAnalysisService(session).get_dashboard()


@router.get("/frequencies", response_model=list[FrequencyResponse])
def frequencies(session: Session = Depends(get_session)) -> list[FrequencyResponse]:
    return FrequencyAnalysisService(session).list_frequencies()


@router.get("/trends", response_model=list[TrendResponse])
def trends(session: Session = Depends(get_session)) -> list[TrendResponse]:
    return FrequencyAnalysisService(session).list_trends()


@router.get("/knowledge-overview", response_model=KnowledgeAnalysisResponse)
def knowledge_overview(
    subject_id: int | None = Query(default=None),
    year_from: int | None = Query(default=None),
    year_to: int | None = Query(default=None),
    question_type: str | None = Query(default=None),
    paper_type: str | None = Query(default=None),
    region: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> KnowledgeAnalysisResponse:
    return FrequencyAnalysisService(session).get_knowledge_analysis(
        subject_id=subject_id,
        year_from=year_from,
        year_to=year_to,
        question_type=question_type,
        paper_type=paper_type,
        region=region,
    )


@router.get("/jobs/{job_id}", response_model=AnalysisJobResponse)
def get_job(job_id: int, session: Session = Depends(get_session)) -> AnalysisJobResponse:
    return FrequencyAnalysisService(session).get_job(job_id)


@router.get("/reports", response_model=list[ReportResponse])
def reports(session: Session = Depends(get_session)) -> list[ReportResponse]:
    return FrequencyAnalysisService(session).list_reports()


@router.post("/reports/generate", response_model=ReportResponse)
def generate_report(
    payload: GenerateReportRequest,
    session: Session = Depends(get_session),
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "operator")),
) -> ReportResponse:
    result = FrequencyAnalysisService(session).generate_report(payload)
    AuditService(session).log(
        current_user,
        module="analysis",
        action="generate_report",
        target_type="report",
        target_id=result.id,
        payload=payload.model_dump(),
    )
    return result


@router.get("/reports/{report_id}/export.md", response_class=PlainTextResponse)
def export_report(report_id: int, session: Session = Depends(get_session)) -> str:
    return FrequencyAnalysisService(session).export_report_markdown(report_id)
