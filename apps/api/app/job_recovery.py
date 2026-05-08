from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AnalysisJob, Asset, ExamPaper


_IN_PROCESS_ANALYSIS_JOB_TYPES = {"paper_parse", "library_parse"}
_INTERRUPTED_JOB_STATUSES = ("pending", "running")
_INTERRUPTED_JOB_MESSAGE = "服务已重启，后台任务已中断，请重新发起。"
_RUNTIME_PAPER_STATUSES = {
    "preparing",
    "reading_file",
    "ocr_running",
    "layout_analyzing",
    "ocr_fallback_running",
    "splitting_questions",
    "building_sections",
    "tagging",
    "saving",
    "parsing",
}
_RUNTIME_ASSET_STATUSES = {
    "preparing",
    "reading_file",
    "ocr_running",
    "layout_analyzing",
    "ocr_fallback_running",
    "splitting_questions",
    "building_sections",
    "tagging",
    "saving",
    "parsing",
}


def fail_interrupted_analysis_jobs(session: Session) -> int:
    stmt = (
        select(AnalysisJob)
        .where(
            AnalysisJob.job_type.in_(_IN_PROCESS_ANALYSIS_JOB_TYPES),
            AnalysisJob.status.in_(_INTERRUPTED_JOB_STATUSES),
        )
        .order_by(AnalysisJob.id.asc())
    )
    jobs = list(session.scalars(stmt))
    if not jobs:
        return 0

    finished_at = datetime.utcnow()
    recovered_count = 0
    for job in jobs:
        scope = dict(job.scope_config_json or {})
        scope["stage"] = "failed"
        detail = dict(scope.get("detail") or {})
        detail["termination_reason"] = "service_restarted"
        scope["detail"] = detail
        job.scope_config_json = scope
        job.status = "failed"
        job.progress = 100
        job.error_message = _INTERRUPTED_JOB_MESSAGE[:255]
        job.finished_at = finished_at
        if job.scope_type == "paper" and job.job_type == "paper_parse":
            _fail_interrupted_paper_parse(session, scope)
        recovered_count += 1

    session.commit()
    return recovered_count


def sync_paper_parse_job_statuses(session: Session) -> int:
    stmt = (
        select(AnalysisJob)
        .where(
            AnalysisJob.job_type == "paper_parse",
            AnalysisJob.scope_type == "paper",
        )
        .order_by(AnalysisJob.id.desc())
    )
    latest_job_by_paper: dict[int, AnalysisJob] = {}
    for job in session.scalars(stmt):
        paper_id = _paper_id_from_scope(job.scope_config_json or {})
        if paper_id is None or paper_id in latest_job_by_paper:
            continue
        latest_job_by_paper[paper_id] = job

    updated_count = 0
    for paper_id, job in latest_job_by_paper.items():
        if _sync_paper_parse_job_status(session, paper_id, job):
            updated_count += 1

    if updated_count:
        session.commit()
    return updated_count


def _sync_paper_parse_job_status(session: Session, paper_id: int, job: AnalysisJob) -> bool:
    paper = session.get(ExamPaper, paper_id)
    if paper is None:
        return False

    changed = False
    if job.job_type == "paper_parse":
        if job.status == "completed" and paper.status != "parsed":
            paper.status = "parsed"
            changed = True
        elif job.status == "failed" and paper.status in _RUNTIME_PAPER_STATUSES:
            paper.status = "parse_failed"
            changed = True

    asset = session.get(Asset, paper.asset_id) if paper.asset_id is not None else None
    if asset is None:
        return changed

    if job.job_type == "paper_parse":
        if job.status == "completed":
            if asset.parse_status != "parsed":
                asset.parse_status = "parsed"
                changed = True
            if asset.ocr_status != "completed":
                asset.ocr_status = "completed"
                changed = True
        elif job.status == "failed":
            if asset.parse_status in _RUNTIME_ASSET_STATUSES:
                asset.parse_status = "failed"
                changed = True
            if asset.ocr_status == "running":
                asset.ocr_status = "failed"
                changed = True
    return changed


def _fail_interrupted_paper_parse(session: Session, scope: dict[str, object]) -> None:
    paper_id = _paper_id_from_scope(scope)
    if paper_id is None:
        return

    paper = session.get(ExamPaper, paper_id)
    if paper is None:
        return

    paper.status = "parse_failed"
    if paper.asset_id is None:
        return
    asset = session.get(Asset, paper.asset_id)
    if asset is None:
        return
    asset.parse_status = "failed"
    asset.ocr_status = "failed"


def _paper_id_from_scope(scope: dict[str, object]) -> int | None:
    try:
        paper_id = int(scope.get("paper_id") or 0)
    except (TypeError, ValueError):
        return None
    return paper_id if paper_id > 0 else None
