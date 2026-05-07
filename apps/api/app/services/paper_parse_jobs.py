from __future__ import annotations

import threading
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import AnalysisJob
from app.services.papers import PaperService
from app.services.system import SystemService
from library.parse_options import DocumentParseOptions


def start_paper_parse_job(session: Session, paper_id: int, options: DocumentParseOptions) -> AnalysisJob:
    tenant_id = _default_tenant_id(session)
    paper = PaperService(session).repository.get_paper(paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="试卷不存在")

    job = AnalysisJob(
        tenant_id=tenant_id,
        subject_id=paper.subject_id,
        job_type="paper_parse",
        scope_type="paper",
        scope_config_json={
            "paper_id": paper_id,
            "parse_options": options.normalized_dump(),
            "stage": "queued",
        },
        status="pending",
        progress=0,
        result_summary_json=None,
        error_message=None,
        created_by=None,
        updated_by=None,
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    thread = threading.Thread(
        target=_run_paper_parse_job,
        args=(job.id, paper_id, options.normalized_dump()),
        name=f"paper-parse-job-{job.id}",
        daemon=True,
    )
    thread.start()
    return job


def _run_paper_parse_job(job_id: int, paper_id: int, options_dump: dict[str, object]) -> None:
    with SessionLocal() as session:
        options = DocumentParseOptions(**options_dump)
        _update_job(
            session,
            job_id,
            status="running",
            progress=3,
            stage="device_check",
            detail={"paper_id": paper_id},
            started_at=datetime.utcnow(),
        )
        try:
            capability = SystemService().get_ocr_capability()
            _update_job(
                session,
                job_id,
                status="running",
                progress=5,
                stage="device_check",
                detail={
                    "capability_status": capability.status,
                    "device_name": capability.device_name,
                    "gpu_memory_total_mb": capability.gpu_memory_total_mb,
                    "gpu_memory_free_mb": capability.gpu_memory_free_mb,
                    "warnings": capability.warnings,
                },
            )

            def progress_callback(stage: str, progress: int, detail: dict[str, object] | None) -> None:
                _update_job(session, job_id, status="running", progress=progress, stage=stage, detail=detail)

            result = PaperService(session).parse_paper(
                paper_id,
                options=options,
                progress_callback=progress_callback,
            )
            _update_job(
                session,
                job_id,
                status="completed",
                progress=100,
                stage="completed",
                detail={
                    "paper_id": result.paper_id,
                    "question_count": result.question_count,
                    "section_count": result.section_count,
                    "tagged_count": result.tagged_count,
                    "provider": result.provider,
                    "warnings": result.warnings,
                },
                result_summary=result.model_dump(mode="json"),
                finished_at=datetime.utcnow(),
            )
        except Exception as exc:
            session.rollback()
            _update_job(
                session,
                job_id,
                status="failed",
                progress=100,
                stage="failed",
                detail={"paper_id": paper_id},
                error_message=str(exc),
                finished_at=datetime.utcnow(),
            )


def _update_job(
    session: Session,
    job_id: int,
    *,
    status: str,
    progress: int,
    stage: str,
    detail: dict[str, object] | None = None,
    result_summary: dict[str, object] | None = None,
    error_message: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> None:
    job = session.get(AnalysisJob, job_id)
    if job is None:
        return
    scope = dict(job.scope_config_json or {})
    scope["stage"] = stage
    if detail:
        scope["detail"] = detail
    job.scope_config_json = scope
    job.status = status
    job.progress = max(0, min(100, progress))
    if result_summary is not None:
        job.result_summary_json = result_summary
    if error_message is not None:
        job.error_message = error_message[:255]
    if started_at is not None:
        job.started_at = started_at
    if finished_at is not None:
        job.finished_at = finished_at
    session.commit()


def _default_tenant_id(session: Session) -> int:
    settings = get_settings()
    tenant = PaperService(session).repository.get_default_tenant(settings.app.default_tenant_code)
    if tenant is None:
        raise HTTPException(status_code=500, detail="默认租户尚未初始化")
    return tenant.id
