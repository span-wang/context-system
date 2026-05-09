from __future__ import annotations

import logging
import time
from datetime import datetime

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import AnalysisJob


logger = logging.getLogger(__name__)


def update_job(
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


def update_job_record(
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
    best_effort: bool = False,
) -> bool:
    max_attempts = 1 if best_effort else 4
    for attempt in range(1, max_attempts + 1):
        try:
            with SessionLocal() as session:
                update_job(
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
            return True
        except OperationalError as exc:
            if attempt == max_attempts:
                raise
            if best_effort:
                logger.debug(
                    "Skipped transient progress update for job %s at stage %s because the database was temporarily unavailable.",
                    job_id,
                    stage,
                )
                return False
            time.sleep(0.2 * attempt)
    return False
