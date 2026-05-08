from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import AnalysisJob, ExamQuestion, QuestionKnowledgeLink
from app.repositories.papers import PaperRepository
from app.services.analysis_jobs import update_job_record
from app.services.question_enrichment import apply_ai_tags_batch


AI_TAG_BATCH_SIZE = 6


class TaggingJobAbortedError(RuntimeError):
    pass


@dataclass(slots=True)
class PaperTaggingResult:
    paper_id: int
    question_count: int
    ai_candidate_question_count: int
    completed_question_count: int
    tagged_count: int

    def to_summary(self) -> dict[str, object]:
        return {
            "paper_id": self.paper_id,
            "question_count": self.question_count,
            "ai_candidate_question_count": self.ai_candidate_question_count,
            "completed_question_count": self.completed_question_count,
            "tagged_count": self.tagged_count,
        }


def start_paper_tagging_job(
    session: Session,
    paper_id: int,
    *,
    question_count: int,
    ai_candidate_question_count: int,
) -> AnalysisJob | None:
    if ai_candidate_question_count <= 0:
        return None

    repository = PaperRepository(session)
    paper = repository.get_paper(paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="试卷不存在")
    active_job = repository.find_active_job(paper_id, "paper_tagging")
    if active_job is not None:
        return active_job

    job = AnalysisJob(
        tenant_id=paper.tenant_id,
        subject_id=paper.subject_id,
        job_type="paper_tagging",
        scope_type="paper",
        scope_config_json={
            "paper_id": paper_id,
            "question_count": question_count,
            "ai_candidate_question_count": ai_candidate_question_count,
            "stage": "queued",
            "detail": {
                "paper_id": paper_id,
                "question_count": question_count,
                "ai_candidate_question_count": ai_candidate_question_count,
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

    thread = threading.Thread(
        target=_run_paper_tagging_job,
        args=(job.id, paper_id),
        name=f"paper-tagging-job-{job.id}",
        daemon=True,
    )
    thread.start()
    return job


def _run_paper_tagging_job(job_id: int, paper_id: int) -> None:
    with SessionLocal() as session:
        if _job_should_stop(job_id, paper_id):
            return
        update_job_record(
            job_id,
            status="running",
            progress=3,
            stage="tagging",
            detail={"paper_id": paper_id, "tagged_questions": 0},
            started_at=datetime.utcnow(),
        )
        try:
            result = _tag_paper_questions(session, job_id, paper_id)
            if _job_should_stop(job_id, paper_id):
                raise TaggingJobAbortedError("试卷已删除或重跑，考点标注任务已终止")
            update_job_record(
                job_id,
                status="completed",
                progress=100,
                stage="completed",
                detail=result.to_summary(),
                result_summary=result.to_summary(),
                finished_at=datetime.utcnow(),
            )
        except TaggingJobAbortedError:
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
                detail={"paper_id": paper_id},
                error_message=str(exc),
                finished_at=datetime.utcnow(),
            )


def _tag_paper_questions(session: Session, job_id: int, paper_id: int) -> PaperTaggingResult:
    repository = PaperRepository(session)
    paper = repository.get_paper(paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="试卷不存在")
    subject_id = paper.subject_id
    if subject_id is None:
        raise HTTPException(status_code=422, detail="试卷未绑定学科，无法执行考点标注")

    points = repository.list_knowledge_points(subject_id)
    questions = repository.list_questions(paper_id)
    linked_question_ids = {
        row[0]
        for row in session.query(QuestionKnowledgeLink.question_id)
        .join(ExamQuestion, ExamQuestion.id == QuestionKnowledgeLink.question_id)
        .filter(ExamQuestion.paper_id == paper_id)
        .all()
    }
    ai_candidates = [question for question in questions if question.id not in linked_question_ids]
    total = len(ai_candidates)
    tagged_count = 0

    if total == 0:
        return PaperTaggingResult(
            paper_id=paper_id,
            question_count=len(questions),
            ai_candidate_question_count=0,
            completed_question_count=0,
            tagged_count=0,
        )

    for batch_start in range(0, total, AI_TAG_BATCH_SIZE):
        if _job_should_stop(job_id, paper_id):
            raise TaggingJobAbortedError("试卷已删除或重跑，考点标注任务已终止")
        batch = ai_candidates[batch_start : batch_start + AI_TAG_BATCH_SIZE]
        batch_result = apply_ai_tags_batch(session, batch, points, paper.tenant_id, None)
        tagged_count += sum(len(items) for items in batch_result.values())
        session.commit()
        completed_count = min(total, batch_start + len(batch))
        current_question_no = batch[-1].question_no if batch else None
        update_job_record(
            job_id,
            status="running",
            progress=min(99, 5 + int((completed_count / max(1, total)) * 94)),
            stage="tagging",
            detail={
                "paper_id": paper_id,
                "question_count": len(questions),
                "ai_candidate_question_count": total,
                "tagged_questions": completed_count,
                "current_question_no": current_question_no,
                "tagged_count": tagged_count,
                "batch_size": len(batch),
            },
            best_effort=True,
        )

    return PaperTaggingResult(
        paper_id=paper_id,
        question_count=len(questions),
        ai_candidate_question_count=total,
        completed_question_count=total,
        tagged_count=tagged_count,
    )


def _job_should_stop(job_id: int, paper_id: int) -> bool:
    with SessionLocal() as session:
        job = session.get(AnalysisJob, job_id)
        if job is None:
            return True
        if job.status not in {"pending", "running"}:
            return True
        paper = PaperRepository(session).get_paper(paper_id)
        return paper is None
