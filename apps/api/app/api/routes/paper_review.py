from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.services.audit import AuditService
from app.schemas.paper_review import (
    PaperReviewAIActionResponse,
    PaperReviewAIBatchActionRequest,
    PaperReviewAIBatchActionResponse,
    PaperReviewAIStandardizeJobResponse,
    PaperReviewAIStandardizeJobSubmitResponse,
    PaperReviewBatchReviewRequest,
    PaperReviewBatchReviewResponse,
    PaperReviewAutoTagResponse,
    PaperReviewAutoTagJobResponse,
    PaperReviewQuestionKnowledgePointUpdateRequest,
    PaperReviewQuestionResponse,
    PaperReviewQuestionUpdateRequest,
    PaperReviewWorkspaceResponse,
)
from app.services.paper_review import PaperReviewService
from app.services.paper_review_standardize_jobs import (
    build_paper_review_ai_standardize_job_response,
    build_paper_review_ai_standardize_job_submit_response,
    get_paper_review_ai_standardize_job,
    start_paper_review_ai_standardize_jobs,
)
from app.services.paper_review_tag_jobs import get_paper_review_auto_tag_job, start_paper_review_auto_tag_job


router = APIRouter(prefix="/api/paper-review", tags=["paper-review"])


@router.get("/papers/{paper_id}", response_model=PaperReviewWorkspaceResponse)
def get_paper_review_workspace(paper_id: int, session: Session = Depends(get_session)) -> PaperReviewWorkspaceResponse:
    return PaperReviewService(session).get_workspace(paper_id)


@router.post("/papers/{paper_id}/auto-tag", response_model=PaperReviewAutoTagJobResponse)
def auto_tag_paper_review_questions(paper_id: int, session: Session = Depends(get_session)) -> PaperReviewAutoTagJobResponse:
    job = start_paper_review_auto_tag_job(session, paper_id=paper_id)
    AuditService(session).log(
        None,
        module="paper_review",
        action="auto_tag",
        target_type="paper",
        target_id=paper_id,
        payload={"job_id": job.id},
    )
    return PaperReviewAutoTagJobResponse(job_id=job.id, paper_id=paper_id, status=job.status, progress=job.progress)


@router.post("/questions/{question_id}/auto-tag", response_model=PaperReviewAutoTagJobResponse)
def auto_tag_single_paper_review_question(question_id: int, session: Session = Depends(get_session)) -> PaperReviewAutoTagJobResponse:
    question = PaperReviewService(session).repository.get_question(question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="题目不存在")
    job = start_paper_review_auto_tag_job(session, paper_id=question.paper_id, force_question_id=question_id)
    AuditService(session).log(
        None,
        module="paper_review",
        action="auto_tag_single",
        target_type="paper_review_question",
        target_id=question_id,
        payload={"job_id": job.id},
    )
    return PaperReviewAutoTagJobResponse(job_id=job.id, paper_id=question.paper_id, status=job.status, progress=job.progress)


@router.get("/auto-tag-jobs/{job_id}", response_model=PaperReviewAutoTagResponse)
def get_paper_review_auto_tagging_job(job_id: int, session: Session = Depends(get_session)) -> PaperReviewAutoTagResponse:
    job = get_paper_review_auto_tag_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    summary = job.result_summary_json or {}
    detail = (job.scope_config_json or {}).get("detail") or {}
    paper_id = int(detail.get("paper_id") or (job.scope_config_json or {}).get("paper_id") or 0)
    requested_count = int(detail.get("total") or summary.get("requested_count") or 0)
    updated_count = int(detail.get("updated_count") or summary.get("updated_count") or 0)
    failed_count = int(detail.get("failed_count") or summary.get("failed_count") or 0)
    skipped_count = int(detail.get("skipped_count") or summary.get("skipped_count") or 0)
    message = str(summary.get("message") or job.error_message or "")
    if not message:
        message = f"总数 {requested_count}，已完成 {updated_count + failed_count}。"
    return PaperReviewAutoTagResponse(
        paper_id=paper_id,
        status=job.status,
        progress=job.progress,
        requested_count=requested_count,
        updated_count=updated_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        message=message,
    )


@router.post("/papers/{paper_id}/ai-standardize-jobs", response_model=PaperReviewAIStandardizeJobSubmitResponse)
def start_paper_review_ai_standardize_jobs_for_paper(
    paper_id: int,
    session: Session = Depends(get_session),
) -> PaperReviewAIStandardizeJobSubmitResponse:
    jobs = start_paper_review_ai_standardize_jobs(
        session,
        paper_id=paper_id,
        only_missing_solutions=True,
    )
    response = build_paper_review_ai_standardize_job_submit_response(paper_id, jobs)
    AuditService(session).log(
        None,
        module="paper_review",
        action="ai_standardize_jobs_start",
        target_type="paper",
        target_id=paper_id,
        payload={
            "job_count": response.job_count,
            "requested_count": response.requested_count,
            "job_ids": [item.job_id for item in response.jobs],
        },
    )
    return response


@router.get("/ai-standardize-jobs/{job_id}", response_model=PaperReviewAIStandardizeJobResponse)
def get_paper_review_ai_standardize_job_status(
    job_id: int,
    session: Session = Depends(get_session),
) -> PaperReviewAIStandardizeJobResponse:
    job = get_paper_review_ai_standardize_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return build_paper_review_ai_standardize_job_response(job)


@router.post("/questions/batch-review", response_model=PaperReviewBatchReviewResponse)
def batch_review_paper_review_questions(
    payload: PaperReviewBatchReviewRequest,
    session: Session = Depends(get_session),
) -> PaperReviewBatchReviewResponse:
    result = PaperReviewService(session).batch_update_review(payload.question_ids, payload.review_status, payload.review_note)
    AuditService(session).log(
        None,
        module="paper_review",
        action="batch_review",
        target_type="paper_review_question",
        payload={
            "question_ids": payload.question_ids,
            "review_status": payload.review_status,
            "review_note": payload.review_note,
            "requested_count": result.requested_count,
            "success_count": result.success_count,
            "failed_count": result.failed_count,
        },
    )
    return result


@router.patch("/questions/{question_id}", response_model=PaperReviewQuestionResponse)
def update_paper_review_question(
    question_id: int,
    payload: PaperReviewQuestionUpdateRequest,
    session: Session = Depends(get_session),
) -> PaperReviewQuestionResponse:
    result = PaperReviewService(session).update_question(question_id, payload)
    AuditService(session).log(
        None,
        module="paper_review",
        action="manual_update",
        target_type="paper_review_question",
        target_id=question_id,
        payload=payload.model_dump(),
    )
    return result


@router.put("/questions/{question_id}/knowledge-points", response_model=PaperReviewQuestionResponse)
def update_paper_review_question_knowledge_points(
    question_id: int,
    payload: PaperReviewQuestionKnowledgePointUpdateRequest,
    session: Session = Depends(get_session),
) -> PaperReviewQuestionResponse:
    result = PaperReviewService(session).update_question_knowledge_points(question_id, payload)
    AuditService(session).log(
        None,
        module="paper_review",
        action="update_knowledge_points",
        target_type="paper_review_question",
        target_id=question_id,
        payload=payload.model_dump(),
    )
    return result


@router.post("/questions/{question_id}/ai-standardize", response_model=PaperReviewAIActionResponse)
def standardize_paper_review_question(question_id: int, session: Session = Depends(get_session)) -> PaperReviewAIActionResponse:
    result = PaperReviewService(session).standardize_question(question_id)
    AuditService(session).log(
        None,
        module="paper_review",
        action="ai_standardize",
        target_type="paper_review_question",
        target_id=question_id,
        payload={"changed": result.changed, "used_ai": result.used_ai, "message": result.message},
    )
    return result


@router.post("/questions/ai-standardize", response_model=PaperReviewAIBatchActionResponse)
def standardize_paper_review_questions(
    payload: PaperReviewAIBatchActionRequest,
    session: Session = Depends(get_session),
) -> PaperReviewAIBatchActionResponse:
    result = PaperReviewService(session).batch_standardize_questions(payload.question_ids)
    AuditService(session).log(
        None,
        module="paper_review",
        action="ai_standardize_batch",
        target_type="paper_review_question",
        payload={
            "question_ids": payload.question_ids,
            "requested_count": result.requested_count,
            "success_count": result.success_count,
            "failed_count": result.failed_count,
            "changed_count": result.changed_count,
        },
    )
    return result


@router.post("/questions/{question_id}/ai-review", response_model=PaperReviewAIActionResponse)
def review_paper_review_question(question_id: int, session: Session = Depends(get_session)) -> PaperReviewAIActionResponse:
    result = PaperReviewService(session).review_question(question_id)
    AuditService(session).log(
        None,
        module="paper_review",
        action="ai_review",
        target_type="paper_review_question",
        target_id=question_id,
        payload={
            "used_ai": result.used_ai,
            "message": result.message,
            "ai_review_status": result.question.ai_review_status,
        },
    )
    return result


@router.post("/questions/ai-review", response_model=PaperReviewAIBatchActionResponse)
def review_paper_review_questions(
    payload: PaperReviewAIBatchActionRequest,
    session: Session = Depends(get_session),
) -> PaperReviewAIBatchActionResponse:
    result = PaperReviewService(session).batch_review_questions(payload.question_ids)
    AuditService(session).log(
        None,
        module="paper_review",
        action="ai_review_batch",
        target_type="paper_review_question",
        payload={
            "question_ids": payload.question_ids,
            "requested_count": result.requested_count,
            "success_count": result.success_count,
            "failed_count": result.failed_count,
            "used_ai_count": result.used_ai_count,
        },
    )
    return result
