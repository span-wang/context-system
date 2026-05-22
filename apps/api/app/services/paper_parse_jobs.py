from __future__ import annotations

import threading
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import AnalysisJob
from app.schemas.papers import PaperParseExecutionMode
from app.services.analysis_jobs import update_job_record
from app.services.papers import PaperService
from app.services.system import SystemService
from library.parse_options import DocumentParseOptions


class ParseJobAbortedError(RuntimeError):
    pass


def start_paper_parse_job(
    session: Session,
    paper_id: int,
    options: DocumentParseOptions,
    execution_mode: PaperParseExecutionMode = "full_chain",
) -> AnalysisJob:
    tenant_id = _default_tenant_id(session)
    paper = PaperService(session).repository.get_paper(paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="试卷不存在")
    active_job = _find_active_paper_parse_job(session, paper_id)
    if active_job is not None:
        active_scope = active_job.scope_config_json or {}
        active_options = active_scope.get("parse_options") if isinstance(active_scope.get("parse_options"), dict) else {}
        try:
            normalized_active_options = DocumentParseOptions(**active_options).normalized_dump()
        except Exception:
            normalized_active_options = active_options
        active_execution_mode = str(active_scope.get("execution_mode") or "full_chain").strip() or "full_chain"
        if normalized_active_options == options.normalized_dump() and active_execution_mode == execution_mode:
            return active_job
        raise HTTPException(
            status_code=409,
            detail="当前已有进行中的解析任务，且解析参数不同，请等待当前任务结束后再发起新的解析。",
        )
    _delete_previous_paper_parse_jobs(session, paper_id)

    job = AnalysisJob(
        tenant_id=tenant_id,
        subject_id=paper.subject_id,
        job_type="paper_parse",
        scope_type="paper",
        scope_config_json={
            "paper_id": paper_id,
            "execution_mode": execution_mode,
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
        args=(job.id, paper_id, options.normalized_dump(), execution_mode),
        name=f"paper-parse-job-{job.id}",
        daemon=True,
    )
    thread.start()
    return job


def _run_paper_parse_job(
    job_id: int,
    paper_id: int,
    options_dump: dict[str, object],
    execution_mode: PaperParseExecutionMode,
) -> None:
    with SessionLocal() as session:
        options = DocumentParseOptions(**options_dump)
        if _job_should_stop(job_id, paper_id):
            return
        update_job_record(
            job_id,
            status="running",
            progress=3,
            stage="device_check",
            detail={"paper_id": paper_id, "execution_mode": execution_mode},
            started_at=datetime.utcnow(),
        )
        try:
            capability = SystemService().get_ocr_capability()
            update_job_record(
                job_id,
                status="running",
                progress=5,
                stage="device_check",
                detail={
                    "execution_mode": execution_mode,
                    "capability_status": capability.status,
                    "device_name": capability.device_name,
                    "gpu_memory_total_mb": capability.gpu_memory_total_mb,
                    "gpu_memory_free_mb": capability.gpu_memory_free_mb,
                    "warnings": capability.warnings,
                },
            )

            def progress_callback(stage: str, progress: int, detail: dict[str, object] | None) -> None:
                if _job_should_stop(job_id, paper_id):
                    raise ParseJobAbortedError("试卷已删除，解析任务已终止")
                update_job_record(
                    job_id,
                    status="running",
                    progress=progress,
                    stage=stage,
                    detail={"execution_mode": execution_mode, **(detail or {})},
                    best_effort=True,
                )

            result = PaperService(session).parse_paper(
                paper_id,
                options=options,
                execution_mode=execution_mode,
                progress_callback=progress_callback,
            )
            if _job_should_stop(job_id, paper_id):
                raise ParseJobAbortedError("试卷已删除，解析任务已终止")
            update_job_record(
                job_id,
                status="completed",
                progress=100,
                stage="completed",
                detail={
                    "paper_id": result.paper_id,
                    "execution_mode": execution_mode,
                    "question_count": result.question_count,
                    "section_count": result.section_count,
                    "tagged_count": result.tagged_count,
                    "provider": result.provider,
                    "token_count": result.token_count,
                    "warnings": result.warnings,
                },
                result_summary=result.model_dump(mode="json"),
                finished_at=datetime.utcnow(),
            )
            _prune_paper_parse_history(paper_id, keep_job_id=job_id)
        except ParseJobAbortedError:
            session.rollback()
        except Exception as exc:
            session.rollback()
            if _job_should_stop(job_id, paper_id):
                return
            update_job_record(
                job_id,
                status="failed",
                progress=100,
                stage="failed",
                detail={"paper_id": paper_id, "execution_mode": execution_mode},
                error_message=str(exc),
                finished_at=datetime.utcnow(),
            )
            _prune_paper_parse_history(paper_id, keep_job_id=job_id)

def _default_tenant_id(session: Session) -> int:
    settings = get_settings()
    tenant = PaperService(session).repository.get_default_tenant(settings.app.default_tenant_code)
    if tenant is None:
        raise HTTPException(status_code=500, detail="默认租户尚未初始化")
    return tenant.id


def _find_active_paper_parse_job(session: Session, paper_id: int) -> AnalysisJob | None:
    return PaperService(session).repository.find_active_job(paper_id, "paper_parse")


def _delete_previous_paper_parse_jobs(session: Session, paper_id: int) -> None:
    repository = PaperService(session).repository
    for job in repository.list_jobs(paper_id, job_type="paper_parse"):
        session.delete(job)
    if hasattr(session, "flush"):
        session.flush()


def _prune_paper_parse_history(paper_id: int, *, keep_job_id: int) -> None:
    with SessionLocal() as session:
        repository = PaperService(session).repository
        changed = False
        for job in repository.list_jobs(paper_id, job_type="paper_parse"):
            if job.id == keep_job_id:
                continue
            session.delete(job)
            changed = True
        if changed:
            session.commit()


def _job_should_stop(job_id: int, paper_id: int) -> bool:
    with SessionLocal() as session:
        job = session.get(AnalysisJob, job_id)
        if job is None:
            return True
        if job.status not in {"pending", "running"}:
            return True
        paper = PaperService(session).repository.get_paper(paper_id)
        return paper is None
