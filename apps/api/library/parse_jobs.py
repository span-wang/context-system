from __future__ import annotations

import asyncio
import threading
from datetime import datetime
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import AnalysisJob, Tenant
from deps import get_library_service
from library.parse_options import DocumentParseOptions


LibraryParseMode = Literal["preview", "reparse"]


def start_library_parse_job(
    file_id: str,
    *,
    mode: LibraryParseMode,
    max_chars: int,
    options: DocumentParseOptions,
) -> AnalysisJob:
    file = get_library_service().get_file(file_id)
    options_dump = options.normalized_dump()
    with SessionLocal() as session:
        active_job = _find_active_library_parse_job(session, file_id, mode, max_chars, options_dump)
        if active_job is not None:
            session.expunge(active_job)
            return active_job

        job = AnalysisJob(
            tenant_id=_default_tenant_id(session),
            subject_id=None,
            job_type="library_parse",
            scope_type="library_file",
            scope_config_json={
                "file_id": file_id,
                "filename": file.filename,
                "mode": mode,
                "max_chars": max_chars,
                "parse_options": options_dump,
                "stage": "queued",
                "detail": {
                    "file_id": file_id,
                    "filename": file.filename,
                    "mode": mode,
                },
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
        job_id = job.id
        session.expunge(job)

        thread = threading.Thread(
            target=_run_library_parse_job,
            args=(job_id, file_id, mode, max_chars, options_dump),
            name=f"library-parse-job-{job_id}",
            daemon=True,
        )
        thread.start()
        return job


def get_library_parse_job(job_id: int) -> AnalysisJob:
    with SessionLocal() as session:
        job = session.get(AnalysisJob, job_id)
        if job is None or job.job_type != "library_parse":
            raise HTTPException(status_code=404, detail="素材解析任务不存在")
        session.expunge(job)
        return job


def _run_library_parse_job(
    job_id: int,
    file_id: str,
    mode: LibraryParseMode,
    max_chars: int,
    options_dump: dict[str, object],
) -> None:
    options = DocumentParseOptions(**options_dump)
    _update_job_record(
        job_id,
        status="running",
        progress=3,
        stage="prepare",
        detail={"file_id": file_id, "mode": mode},
        started_at=datetime.utcnow(),
    )
    try:

        def progress_callback(stage: str, progress: int, detail: dict[str, object] | None) -> None:
            payload = {
                "file_id": file_id,
                "mode": mode,
                **(detail or {}),
            }
            _update_job_record(job_id, status="running", progress=progress, stage=stage, detail=payload)

        result = asyncio.run(
            _execute_library_parse(
                file_id=file_id,
                mode=mode,
                max_chars=max_chars,
                options=options,
                progress_callback=progress_callback,
            )
        )
        _update_job_record(
            job_id,
            status="completed",
            progress=100,
            stage="completed",
            detail=_summary_detail(file_id, mode, result),
            result_summary=result,
            finished_at=datetime.utcnow(),
        )
    except Exception as exc:
        _update_job_record(
            job_id,
            status="failed",
            progress=100,
            stage="failed",
            detail={"file_id": file_id, "mode": mode},
            error_message=_error_message(exc),
            finished_at=datetime.utcnow(),
        )


async def _execute_library_parse(
    *,
    file_id: str,
    mode: LibraryParseMode,
    max_chars: int,
    options: DocumentParseOptions,
    progress_callback,
) -> dict:
    service = get_library_service()
    if mode == "reparse":
        return await service.reparse(
            file_id,
            max_chars=max_chars,
            options=options,
            progress_callback=progress_callback,
        )
    return await service.preview(
        file_id,
        max_chars=max_chars,
        options=options,
        progress_callback=progress_callback,
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
        merged_detail = dict(scope.get("detail") or {})
        merged_detail.update(detail)
        scope["detail"] = merged_detail
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


def _update_job_record(
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
    with SessionLocal() as session:
        _update_job(
            session,
            job_id,
            status=status,
            progress=progress,
            stage=stage,
            detail=detail,
            result_summary=result_summary,
            error_message=error_message,
            started_at=started_at,
            finished_at=finished_at,
        )


def _summary_detail(file_id: str, mode: LibraryParseMode, result: dict[str, object]) -> dict[str, object]:
    return {
        "file_id": file_id,
        "mode": mode,
        "provider": str(result.get("provider") or "-"),
        "token_count": int(result.get("token_count") or 0),
        "table_count": int(result.get("table_count") or 0),
        "warning_count": int(result.get("warning_count") or 0),
        "stored_sequence_number": int(result.get("stored_sequence_number") or 0),
    }


def _default_tenant_id(session: Session) -> int:
    settings = get_settings()
    tenant = session.scalar(select(Tenant).where(Tenant.code == settings.app.default_tenant_code))
    if tenant is None:
        raise HTTPException(status_code=500, detail="默认租户尚未初始化")
    return tenant.id


def _find_active_library_parse_job(
    session: Session,
    file_id: str,
    mode: LibraryParseMode,
    max_chars: int,
    options_dump: dict[str, object],
) -> AnalysisJob | None:
    stmt = (
        select(AnalysisJob)
        .where(
            AnalysisJob.job_type == "library_parse",
            AnalysisJob.scope_type == "library_file",
            AnalysisJob.status.in_(("pending", "running")),
        )
        .order_by(AnalysisJob.id.desc())
    )
    for job in session.scalars(stmt):
        scope = job.scope_config_json or {}
        if (
            scope.get("file_id") == file_id
            and scope.get("mode") == mode
            and scope.get("max_chars") == max_chars
            and scope.get("parse_options") == options_dump
        ):
            return job
    return None


def _error_message(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if detail:
        return str(detail)
    message = str(exc).strip()
    return message or exc.__class__.__name__
