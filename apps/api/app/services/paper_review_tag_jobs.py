from __future__ import annotations

import threading
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import AnalysisJob
from app.services.analysis_jobs import update_job_record
from app.services.paper_review import PaperReviewService
from app.services.papers import PaperService


def start_paper_review_auto_tag_job(
    session: Session,
    *,
    paper_id: int,
    force_question_id: int | None = None,
) -> AnalysisJob:
    tenant_id = _default_tenant_id(session)
    paper = PaperReviewService(session).repository.get_paper(paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="试卷不存在")
    active_job = _find_active_auto_tag_job(session, paper_id, force_question_id=force_question_id)
    if active_job is not None:
        return active_job

    scope = {
        "paper_id": paper_id,
        "stage": "queued",
    }
    if force_question_id is not None:
        scope["force_question_id"] = force_question_id
    job = AnalysisJob(
        tenant_id=tenant_id,
        subject_id=paper.subject_id,
        job_type="paper_review_auto_tag",
        scope_type="paper",
        scope_config_json=scope,
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
        target=_run_paper_review_auto_tag_job,
        args=(job.id, paper_id, force_question_id),
        name=f"paper-review-auto-tag-job-{job.id}",
        daemon=True,
    )
    thread.start()
    return job


def get_paper_review_auto_tag_job(job_id: int) -> AnalysisJob | None:
    with SessionLocal() as session:
        return session.get(AnalysisJob, job_id)


def _run_paper_review_auto_tag_job(job_id: int, paper_id: int, force_question_id: int | None) -> None:
    with SessionLocal() as session:
        update_job_record(
            job_id,
            status="running",
            progress=2,
            stage="prepare",
            detail={"paper_id": paper_id, "force_question_id": force_question_id},
            started_at=datetime.utcnow(),
        )
        try:
            service = PaperReviewService(session)
            result = service.auto_tag_paper_questions(
                paper_id,
                force_question_id=force_question_id,
                progress_callback=lambda current, total, updated, failed, skipped: update_job_record(
                    job_id,
                    status="running",
                    progress=(100 if total <= 0 else max(3, min(99, int(current * 100 / total)))),
                    stage="tagging",
                    detail={
                        "paper_id": paper_id,
                        "force_question_id": force_question_id,
                        "total": total,
                        "completed": current,
                        "updated_count": updated,
                        "failed_count": failed,
                        "skipped_count": skipped,
                    },
                    best_effort=True,
                ),
            )
            update_job_record(
                job_id,
                status="completed",
                progress=100,
                stage="completed",
                detail={
                    "paper_id": paper_id,
                    "force_question_id": force_question_id,
                    "total": result.requested_count,
                    "completed": result.requested_count,
                    "updated_count": result.updated_count,
                    "failed_count": result.failed_count,
                    "skipped_count": result.skipped_count,
                },
                result_summary=result.model_dump(mode="json"),
                finished_at=datetime.utcnow(),
            )
        except Exception as exc:
            session.rollback()
            update_job_record(
                job_id,
                status="failed",
                progress=100,
                stage="failed",
                detail={"paper_id": paper_id, "force_question_id": force_question_id},
                error_message=str(exc),
                finished_at=datetime.utcnow(),
            )


def _default_tenant_id(session: Session) -> int:
    settings = get_settings()
    resolved = PaperService(session).repository.get_default_tenant(settings.app.default_tenant_code)
    if resolved is None:
        raise HTTPException(status_code=500, detail="默认租户尚未初始化")
    return resolved.id


def _find_active_auto_tag_job(session: Session, paper_id: int, *, force_question_id: int | None) -> AnalysisJob | None:
    jobs = PaperService(session).repository.list_jobs(paper_id, job_type="paper_review_auto_tag")
    return next(
        (
            job
            for job in jobs
            if job.status in {"pending", "running"}
            and int(((job.scope_config_json or {}).get("paper_id") or 0)) == paper_id
            and (
                (force_question_id is None and (job.scope_config_json or {}).get("force_question_id") is None)
                or (force_question_id is not None and int(((job.scope_config_json or {}).get("force_question_id") or 0)) == force_question_id)
            )
        ),
        None,
    )
