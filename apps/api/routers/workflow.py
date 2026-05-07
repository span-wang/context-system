from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from deps import get_db
from background import enqueue_background_task, register_task_handler
from exporters.xiaohongshu import build_publish_package_from_markdown, render_publish_package
from routers.generate import _create_job, _ensure_context_size, _initial_context, _run_generation, run_review_job
from schemas.generation import GenerationRequest
from schemas.review import ReviewRequest
from schemas.workflow import (
    WorkflowConfirmRequest,
    WorkflowEvent,
    WorkflowExportRequest,
    WorkflowGenerateRequest,
    WorkflowGenerateResponse,
    WorkflowTopic,
    WorkflowTopicCreate,
    WorkflowTopicPatch,
)
from settings import normalize_subject_name


router = APIRouter(prefix="/api/workflow", tags=["workflow"])


@router.get("/topics", response_model=list[WorkflowTopic])
def list_topics(
    status: str | None = Query(None),
    owner: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    search: str | None = Query(None),
) -> list[WorkflowTopic]:
    return get_db().list_topics(status=status, owner=owner, date_from=date_from, date_to=date_to, search=search)


@router.post("/topics", response_model=WorkflowTopic)
def create_topic(request: WorkflowTopicCreate) -> WorkflowTopic:
    payload = request.model_dump()
    payload["subject"] = _normalize_subject_or_422(request.subject)
    _validate_materials(payload.get("material_file_ids") or [])
    now = datetime.utcnow()
    topic = WorkflowTopic(
        id=str(uuid4()),
        created_at=now,
        updated_at=now,
        **payload,
    )
    return get_db().create_topic(topic, actor=topic.owner, note="閫夐鍏ュ簱")


@router.get("/topics/{topic_id}", response_model=WorkflowTopic)
def get_topic(topic_id: str) -> WorkflowTopic:
    topic = get_db().get_topic(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="workflow topic not found")
    return topic


@router.patch("/topics/{topic_id}", response_model=WorkflowTopic)
def update_topic(topic_id: str, patch: WorkflowTopicPatch) -> WorkflowTopic:
    patch = _normalize_patch(patch)
    updated = get_db().update_topic(topic_id, patch)
    if not updated:
        raise HTTPException(status_code=404, detail="workflow topic not found")
    return updated


@router.delete("/topics/{topic_id}")
def delete_topic(topic_id: str) -> dict:
    if not get_db().delete_topic(topic_id):
        raise HTTPException(status_code=404, detail="workflow topic not found")
    return {"ok": True}


@router.post("/topics/{topic_id}/generate", response_model=WorkflowGenerateResponse)
async def generate_topic(topic_id: str, request: WorkflowGenerateRequest) -> WorkflowGenerateResponse:
    topic = _get_topic_or_404(topic_id)
    if request.mode == "direct":
        _validate_materials(topic.material_file_ids)
    generation_request = GenerationRequest(
        mode=request.mode,
        subject=topic.subject,
        category=topic.category,
        chapter=topic.chapter,
        content_type=topic.content_type,
        options={"pages": request.pages, **request.options},
        user_notes=_compose_user_notes(topic, request.user_notes),
        library_file_ids=topic.material_file_ids,
        ragflow_dataset_ids=topic.ragflow_dataset_ids,
    )
    context = await _initial_context(generation_request)
    _ensure_context_size(context)
    job = _create_job(context)
    updated = _update_topic_or_404(
        topic_id,
        WorkflowTopicPatch(
            status="drafting",
            review_status="not_started",
            generation_job_id=job.id,
            note="浠庨€夐鍙戣捣鍐呭鐢熸垚",
            actor=topic.owner,
        ),
        event_type="generation_started",
    )
    _enqueue_topic_generation(topic_id, job.id, generation_request)
    return WorkflowGenerateResponse(topic=updated, job_id=job.id)


@router.post("/topics/{topic_id}/review", response_model=WorkflowTopic)
async def review_topic(topic_id: str, request: ReviewRequest | None = None) -> WorkflowTopic:
    topic = _get_topic_or_404(topic_id)
    if not topic.generation_job_id:
        raise HTTPException(status_code=409, detail="topic has no generation job")
    job = get_db().get_job(topic.generation_job_id)
    if not job or not job.result:
        raise HTTPException(status_code=409, detail="generation result is not ready")
    if job.status == "reviewing":
        raise HTTPException(status_code=409, detail="content review is already running")
    _update_topic_or_404(
        topic_id,
        WorkflowTopicPatch(status="reviewing", review_status="reviewing", note="鍙戣捣鍐呭瀹℃煡", actor=topic.owner),
        event_type="review_started",
    )
    job = get_db().get_job(topic.generation_job_id)
    if not job or not job.result:
        raise HTTPException(status_code=409, detail="generation result is not ready")
    if job.status == "reviewing":
        raise HTTPException(status_code=409, detail="content review is already running")
    job.status = "reviewing"
    job.error = None
    get_db().update_job(job)
    _enqueue_topic_review(topic_id, topic.generation_job_id, request)
    refreshed = _get_topic_or_404(topic_id)
    return refreshed


@router.post("/topics/{topic_id}/confirm", response_model=WorkflowTopic)
def confirm_topic(topic_id: str, request: WorkflowConfirmRequest) -> WorkflowTopic:
    topic = _get_topic_or_404(topic_id)
    return _update_topic_or_404(
        topic_id,
        WorkflowTopicPatch(
            status="approved",
            confirmed_by=request.confirmed_by or topic.owner,
            confirmed_at=datetime.utcnow(),
            note=request.note or "浜哄伐纭閫氳繃",
            actor=request.confirmed_by or topic.owner,
        ),
        event_type="confirmed",
    )


@router.get("/topics/{topic_id}/export")
def download_topic_export(topic_id: str) -> PlainTextResponse:
    return _export_topic(topic_id, WorkflowExportRequest())


@router.post("/topics/{topic_id}/export")
def export_topic(topic_id: str, request: WorkflowExportRequest | None = None) -> PlainTextResponse:
    return _export_topic(topic_id, request or WorkflowExportRequest())


def _export_topic(topic_id: str, request: WorkflowExportRequest) -> PlainTextResponse:
    topic = _get_topic_or_404(topic_id)
    job = get_db().get_job(topic.generation_job_id) if topic.generation_job_id else None
    if not job or not job.result:
        raise HTTPException(status_code=409, detail="topic has no generated result to export")
    events = get_db().list_topic_events(topic_id)
    package = _build_publish_package(topic, job, events)
    if request.mark_exported:
        topic = _update_topic_or_404(
            topic_id,
            WorkflowTopicPatch(
                status="exported",
                note=request.note or "exported publish package",
                actor=request.actor or topic.owner,
            ),
            event_type="exported",
        )
    filename = f"{topic.title or topic.id}.publish.md".replace("/", "_").replace("\\", "_")
    return PlainTextResponse(
        package,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        media_type="text/markdown; charset=utf-8",
    )


@router.get("/topics/{topic_id}/events", response_model=list[WorkflowEvent])
def list_topic_events(topic_id: str) -> list[WorkflowEvent]:
    _get_topic_or_404(topic_id)
    return get_db().list_topic_events(topic_id)


async def _run_topic_generation(topic_id: str, job_id: str, request: GenerationRequest) -> None:
    try:
        await _run_generation(job_id, request)
    except Exception:
        job = get_db().get_job(job_id)
        topic = get_db().get_topic(topic_id)
        if topic and topic.generation_job_id == job_id:
            get_db().update_topic(
                topic_id,
                WorkflowTopicPatch(
                    status="needs_changes",
                    note=(job.error if job else None) or "generation failed",
                    actor=topic.owner,
                ),
                event_type="generation_failed",
            )
        raise
    job = get_db().get_job(job_id)
    if not job:
        return
    topic = get_db().get_topic(topic_id)
    if not topic or topic.generation_job_id != job_id:
        return
    if job.status == "done" and job.result:
        status = "generated"
        note = "generation completed; waiting for review"
        event_type = "generation_completed"
    else:
        status = "needs_changes"
        note = job.error or "鐢熸垚澶辫触"
        event_type = "generation_failed"
    get_db().update_topic(
        topic_id,
        WorkflowTopicPatch(status=status, note=note, actor=topic.owner),
        event_type=event_type,
    )


async def _run_topic_review(topic_id: str, job_id: str, request: ReviewRequest | None = None) -> None:
    topic = get_db().get_topic(topic_id)
    try:
        job = await run_review_job(job_id, request)
        topic = get_db().get_topic(topic_id)
        if not topic or topic.generation_job_id != job_id:
            return
        review_passed = bool(job.review and job.review.pass_overall)
        get_db().update_topic(
            topic_id,
            WorkflowTopicPatch(
                status="awaiting_confirm" if review_passed else "needs_changes",
                review_status="passed" if review_passed else "needs_changes",
                note="content review completed",
                actor=topic.owner,
            ),
            event_type="review_completed",
        )
    except Exception as exc:
        if topic and topic.generation_job_id == job_id:
            get_db().update_topic(
                topic_id,
                WorkflowTopicPatch(
                    status="needs_changes",
                    review_status="needs_changes",
                    note=str(exc),
                    actor=topic.owner,
                ),
                event_type="review_failed",
            )
        raise


def _enqueue_topic_generation(topic_id: str, job_id: str, request: GenerationRequest) -> None:
    enqueue_background_task(
        "topic_generation",
        {
            "topic_id": topic_id,
            "job_id": job_id,
            "request": request.model_dump(mode="json"),
        },
    )


def _enqueue_topic_review(topic_id: str, job_id: str, request: ReviewRequest | None = None) -> None:
    enqueue_background_task(
        "topic_review",
        {
            "topic_id": topic_id,
            "job_id": job_id,
            "request": request.model_dump(mode="json") if request else None,
        },
    )


async def _handle_topic_generation_task(payload: dict) -> None:
    request = GenerationRequest.model_validate(payload["request"])
    await _run_topic_generation(str(payload["topic_id"]), str(payload["job_id"]), request)


async def _handle_topic_review_task(payload: dict) -> None:
    request_data = payload.get("request")
    request = ReviewRequest.model_validate(request_data) if request_data else None
    await _run_topic_review(str(payload["topic_id"]), str(payload["job_id"]), request)


register_task_handler("topic_generation", _handle_topic_generation_task)
register_task_handler("topic_review", _handle_topic_review_task)


def _get_topic_or_404(topic_id: str) -> WorkflowTopic:
    topic = get_db().get_topic(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="workflow topic not found")
    return topic


def _update_topic_or_404(topic_id: str, patch: WorkflowTopicPatch, event_type: str) -> WorkflowTopic:
    updated = get_db().update_topic(topic_id, patch, event_type=event_type)
    if not updated:
        raise HTTPException(status_code=404, detail="workflow topic not found")
    return updated


def _normalize_patch(patch: WorkflowTopicPatch) -> WorkflowTopicPatch:
    updates = patch.model_dump(exclude_unset=True)
    if "subject" in updates and updates["subject"] is not None:
        updates["subject"] = _normalize_subject_or_422(updates["subject"])
    if "material_file_ids" in updates and updates["material_file_ids"] is not None:
        _validate_materials(updates["material_file_ids"])
    return patch.model_copy(update=updates)


def _normalize_subject_or_422(subject: str) -> str:
    normalized = normalize_subject_name(subject)
    if not normalized:
        raise HTTPException(status_code=422, detail=f"unknown subject: {subject}")
    return normalized


def _validate_materials(file_ids: list[str]) -> None:
    missing = [file_id for file_id in file_ids if not get_db().get_library_file(file_id)]
    if missing:
        raise HTTPException(status_code=422, detail=f"unknown material file ids: {', '.join(missing)}")


def _compose_user_notes(topic: WorkflowTopic, extra_notes: str | None) -> str:
    parts = [
        f"Topic: {topic.title}",
        f"Publish channel: {topic.publish_channel}",
    ]
    if topic.brief:
        parts.append(f"Brief: {topic.brief}")
    if topic.content_goal:
        parts.append(f"Content goal: {topic.content_goal}")
    if topic.audience:
        parts.append(f"Audience: {topic.audience}")
    if extra_notes:
        parts.append(f"Extra requirements: {extra_notes}")
    return "\n".join(parts)


def _build_publish_package(topic: WorkflowTopic, job, events: list[WorkflowEvent]) -> str:
    review = job.review
    publish_package = job.result.publish_package or build_publish_package_from_markdown(
        title=job.result.title,
        markdown=job.result.raw_markdown,
        context=job.context,
        sections=job.result.sections,
        unverified=job.result.unverified,
    )
    lines = [
        f"# {topic.title}",
        "",
        "## Publish Info",
        f"- Topic ID: {topic.id}",
        f"- Owner: {topic.owner or 'unassigned'}",
        f"- Publish channel: {topic.publish_channel}",
        f"- Scheduled date: {topic.scheduled_date or 'unscheduled'}",
        f"- Current status: {topic.status}",
        f"- Review status: {topic.review_status}",
        f"- Generation job: {topic.generation_job_id or 'unbound'}",
        "",
        "## Source Materials",
    ]
    if topic.material_file_ids:
        for index, file_id in enumerate(topic.material_file_ids, start=1):
            source = get_db().get_library_file(file_id)
            label = source.source_title or source.filename if source else file_id
            lines.append(f"- [{index}] {label} ({file_id})")
    elif topic.ragflow_dataset_ids:
        lines.extend(f"- RAGFlow dataset: {dataset_id}" for dataset_id in topic.ragflow_dataset_ids)
    else:
        lines.append("- No source material bound")

    lines.extend(
        [
            "",
            "## Review Result",
            f"- Verdict: {('passed' if review.pass_overall else 'needs changes') if review else 'not reviewed'}",
        ]
    )
    if review:
        lines.append(f"- Review mode: {review.mode}")
        lines.append(f"- Issue count: {len(review.issues)}")
        if review.suggestions:
            lines.append("- Suggestions:")
            lines.extend(f"  - {item}" for item in review.suggestions)

    lines.extend(
        [
            "",
            "## Xiaohongshu Publish Package",
            "",
            render_publish_package(publish_package, fallback_title=job.result.title).strip(),
            "",
            "## Version History",
        ]
    )
    for event in events:
        lines.append(f"- v{event.version} {event.created_at.isoformat()} {event.event_type} {event.actor or ''} {event.note or ''}".rstrip())
    return "\n".join(lines).strip() + "\n"

