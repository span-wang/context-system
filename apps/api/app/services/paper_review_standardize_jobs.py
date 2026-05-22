from __future__ import annotations

import threading
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import AnalysisJob, PaperReviewQuestion
from app.schemas.paper_review import (
    PaperReviewAIStandardizeJobItemResponse,
    PaperReviewAIStandardizeJobResponse,
    PaperReviewAIStandardizeJobSubmitResponse,
)
from app.services.analysis_jobs import update_job_record
from app.services.paper_review import (
    PaperReviewService,
    _group_review_questions_by_parent,
    _http_exception_message,
    _leaf_review_descendants,
    _root_review_question,
)


AI_STANDARDIZE_JOB_TYPE = "paper_review_ai_standardize"
AI_STANDARDIZE_BATCH_SIZE = 10


def start_paper_review_ai_standardize_jobs(
    session: Session,
    *,
    paper_id: int,
    question_ids: list[int] | None = None,
    only_missing_solutions: bool = True,
) -> list[AnalysisJob]:
    service = PaperReviewService(session)
    paper = service.repository.get_paper(paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="试卷不存在")
    if question_ids is None and only_missing_solutions:
        active_jobs = _list_active_paper_review_ai_standardize_jobs(session, paper_id=paper_id)
        if active_jobs:
            return active_jobs

    questions = service.repository.list_questions(paper_id)
    question_batches = _build_standardize_question_batches(
        questions,
        question_ids=question_ids,
        only_missing_solutions=only_missing_solutions,
        batch_size=AI_STANDARDIZE_BATCH_SIZE,
    )
    if not question_batches:
        return []

    jobs: list[AnalysisJob] = []
    batch_count = len(question_batches)
    for batch_index, batch_question_ids in enumerate(question_batches, start=1):
        job = AnalysisJob(
            tenant_id=paper.tenant_id,
            subject_id=paper.subject_id,
            job_type=AI_STANDARDIZE_JOB_TYPE,
            scope_type="paper",
            scope_config_json={
                "paper_id": paper_id,
                "question_ids": batch_question_ids,
                "requested_count": len(batch_question_ids),
                "batch_index": batch_index,
                "batch_count": batch_count,
                "only_missing_solutions": only_missing_solutions,
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
        jobs.append(job)

    session.commit()
    for batch_index, (job, batch_question_ids) in enumerate(zip(jobs, question_batches, strict=False), start=1):
        session.refresh(job)
        thread = threading.Thread(
            target=_run_paper_review_ai_standardize_job,
            args=(job.id, paper_id, batch_question_ids, batch_index, batch_count),
            name=f"paper-review-ai-standardize-job-{job.id}",
            daemon=True,
        )
        thread.start()
    return jobs


def cancel_active_paper_review_ai_standardize_jobs(session: Session, *, paper_id: int, reason: str) -> int:
    count = 0
    now = datetime.utcnow()
    stmt = (
        select(AnalysisJob)
        .where(
            AnalysisJob.job_type == AI_STANDARDIZE_JOB_TYPE,
            AnalysisJob.scope_type == "paper",
            AnalysisJob.status.in_(("pending", "running")),
        )
        .order_by(AnalysisJob.id.desc())
    )
    for job in session.scalars(stmt):
        if int(((job.scope_config_json or {}).get("paper_id") or 0)) != paper_id:
            continue
        scope = dict(job.scope_config_json or {})
        detail = dict(scope.get("detail") or {})
        detail.update({"paper_id": paper_id, "cancel_reason": reason})
        scope["stage"] = "cancelled"
        scope["detail"] = detail
        job.scope_config_json = scope
        job.status = "failed"
        job.progress = 100
        job.error_message = reason[:255]
        job.finished_at = now
        count += 1
    if count:
        session.commit()
    return count


def get_paper_review_ai_standardize_job(job_id: int) -> AnalysisJob | None:
    with SessionLocal() as session:
        return session.get(AnalysisJob, job_id)


def build_paper_review_ai_standardize_job_submit_response(
    paper_id: int,
    jobs: list[AnalysisJob],
) -> PaperReviewAIStandardizeJobSubmitResponse:
    requested_count = sum(int(((job.scope_config_json or {}).get("requested_count") or 0)) for job in jobs)
    return PaperReviewAIStandardizeJobSubmitResponse(
        paper_id=paper_id,
        requested_count=requested_count,
        job_count=len(jobs),
        jobs=[
            PaperReviewAIStandardizeJobItemResponse(
                job_id=job.id,
                paper_id=paper_id,
                status=job.status,
                progress=job.progress,
                requested_count=int(((job.scope_config_json or {}).get("requested_count") or 0)),
                batch_index=int(((job.scope_config_json or {}).get("batch_index") or 1)),
                batch_count=int(((job.scope_config_json or {}).get("batch_count") or max(1, len(jobs)))),
                question_ids=_normalize_positive_int_list((job.scope_config_json or {}).get("question_ids") or []),
            )
            for job in jobs
        ],
        message=(
            f"已提交 {len(jobs)} 个异步解题任务，覆盖 {requested_count} 道题。"
            if jobs
            else "当前试卷暂无需要异步解题的题目。"
        ),
    )


def build_paper_review_ai_standardize_job_response(job: AnalysisJob) -> PaperReviewAIStandardizeJobResponse:
    scope = job.scope_config_json or {}
    summary = job.result_summary_json or {}
    detail = scope.get("detail") or {}
    paper_id = int(detail.get("paper_id") or scope.get("paper_id") or 0)
    requested_count = int(summary.get("requested_count") or detail.get("total") or scope.get("requested_count") or 0)
    success_count = int(summary.get("success_count") or detail.get("success_count") or 0)
    failed_count = int(summary.get("failed_count") or detail.get("failed_count") or 0)
    changed_count = int(summary.get("changed_count") or detail.get("changed_count") or 0)
    used_ai_count = int(summary.get("used_ai_count") or detail.get("used_ai_count") or 0)
    completed = int(detail.get("completed") or (success_count + failed_count))
    message = str(summary.get("message") or job.error_message or "").strip()
    if not message:
        message = f"总数 {requested_count}，已完成 {completed}。"
    return PaperReviewAIStandardizeJobResponse(
        job_id=job.id,
        paper_id=paper_id,
        status=job.status,
        progress=job.progress,
        requested_count=requested_count,
        success_count=success_count,
        failed_count=failed_count,
        changed_count=changed_count,
        used_ai_count=used_ai_count,
        batch_index=int(summary.get("batch_index") or scope.get("batch_index") or 1),
        batch_count=int(summary.get("batch_count") or scope.get("batch_count") or 1),
        question_ids=_normalize_positive_int_list(summary.get("question_ids") or scope.get("question_ids") or []),
        message=message,
    )


def _run_paper_review_ai_standardize_job(
    job_id: int,
    paper_id: int,
    question_ids: list[int],
    batch_index: int,
    batch_count: int,
) -> None:
    with SessionLocal() as session:
        total = len(question_ids)
        update_job_record(
            job_id,
            status="running",
            progress=2,
            stage="prepare",
            detail={
                "paper_id": paper_id,
                "total": total,
                "completed": 0,
                "success_count": 0,
                "failed_count": 0,
                "changed_count": 0,
                "used_ai_count": 0,
            },
            started_at=datetime.utcnow(),
        )
        try:
            service = PaperReviewService(session)
            success_count = 0
            failed_count = 0
            changed_count = 0
            used_ai_count = 0
            failures: list[str] = []
            for completed, question_id in enumerate(question_ids, start=1):
                if _job_should_stop(job_id, paper_id):
                    return
                try:
                    result = service.standardize_question(question_id)
                    success_count += 1
                    changed_count += int(result.changed)
                    used_ai_count += int(result.used_ai)
                except HTTPException as exc:
                    failed_count += 1
                    failures.append(_http_exception_message(exc))
                    session.rollback()
                except Exception as exc:
                    failed_count += 1
                    failures.append(str(exc) or "AI 服务执行失败。")
                    session.rollback()
                update_job_record(
                    job_id,
                    status="running",
                    progress=(100 if total <= 0 else max(3, min(99, int(completed * 100 / total)))),
                    stage="standardizing",
                    detail={
                        "paper_id": paper_id,
                        "total": total,
                        "completed": completed,
                        "success_count": success_count,
                        "failed_count": failed_count,
                        "changed_count": changed_count,
                        "used_ai_count": used_ai_count,
                    },
                    best_effort=True,
                )

            message = f"AI 解题已完成：共 {total} 道，成功 {success_count} 道"
            if changed_count:
                message += f"，有更新 {changed_count} 道"
            if failed_count:
                message += f"，失败 {failed_count} 道"
            message += "。"
            if failures:
                message += f" 首个失败：{failures[0]}"

            update_job_record(
                job_id,
                status="completed",
                progress=100,
                stage="completed",
                detail={
                    "paper_id": paper_id,
                    "total": total,
                    "completed": total,
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "changed_count": changed_count,
                    "used_ai_count": used_ai_count,
                },
                result_summary={
                    "paper_id": paper_id,
                    "requested_count": total,
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "changed_count": changed_count,
                    "used_ai_count": used_ai_count,
                    "batch_index": batch_index,
                    "batch_count": batch_count,
                    "question_ids": question_ids,
                    "message": message,
                },
                finished_at=datetime.utcnow(),
            )
        except Exception as exc:
            session.rollback()
            if _job_should_stop(job_id, paper_id):
                return
            update_job_record(
                job_id,
                status="failed",
                progress=100,
                stage="failed",
                detail={"paper_id": paper_id, "total": total},
                error_message=str(exc),
                finished_at=datetime.utcnow(),
            )


def _build_standardize_question_batches(
    questions: list[PaperReviewQuestion],
    *,
    question_ids: list[int] | None,
    only_missing_solutions: bool,
    batch_size: int,
) -> list[list[int]]:
    if batch_size <= 0:
        batch_size = AI_STANDARDIZE_BATCH_SIZE
    ordered_questions = sorted(questions, key=lambda item: (item.sort_order, item.id))
    by_id = {question.id: question for question in ordered_questions}
    children_by_parent = _group_review_questions_by_parent(ordered_questions)
    roots: list[PaperReviewQuestion] = []
    seen_root_ids: set[int] = set()

    if question_ids:
        for raw_question_id in question_ids:
            try:
                question_id = int(raw_question_id)
            except (TypeError, ValueError):
                continue
            question = by_id.get(question_id)
            if question is None:
                continue
            root_question = _root_review_question(question, by_id)
            if root_question.id in seen_root_ids:
                continue
            if only_missing_solutions and not _question_needs_solution(root_question, children_by_parent):
                continue
            seen_root_ids.add(root_question.id)
            roots.append(root_question)
    else:
        for question in ordered_questions:
            if question.parent_question_id is not None:
                continue
            if only_missing_solutions and not _question_needs_solution(question, children_by_parent):
                continue
            roots.append(question)

    return [
        [question.id for question in roots[index:index + batch_size]]
        for index in range(0, len(roots), batch_size)
    ]


def _question_needs_solution(
    question: PaperReviewQuestion,
    children_by_parent: dict[int, list[PaperReviewQuestion]],
) -> bool:
    leaf_questions = _leaf_review_descendants(question, children_by_parent)
    if not leaf_questions:
        return False
    return any(
        not (leaf_question.answer_text or "").strip() or not (leaf_question.analysis_text or "").strip()
        for leaf_question in leaf_questions
    )


def _job_should_stop(job_id: int, paper_id: int) -> bool:
    with SessionLocal() as session:
        job = session.get(AnalysisJob, job_id)
        if job is None:
            return True
        if job.status not in {"pending", "running"}:
            return True
        paper = PaperReviewService(session).repository.get_paper(paper_id)
        return paper is None


def _normalize_positive_int_list(values: list[object]) -> list[int]:
    normalized: list[int] = []
    for value in values:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            normalized.append(number)
    return normalized


def _list_active_paper_review_ai_standardize_jobs(session: Session, *, paper_id: int) -> list[AnalysisJob]:
    stmt = (
        select(AnalysisJob)
        .where(
            AnalysisJob.job_type == AI_STANDARDIZE_JOB_TYPE,
            AnalysisJob.scope_type == "paper",
            AnalysisJob.status.in_(("pending", "running")),
        )
        .order_by(AnalysisJob.id.asc())
    )
    return [
        job
        for job in session.scalars(stmt)
        if int(((job.scope_config_json or {}).get("paper_id") or 0)) == paper_id
    ]
