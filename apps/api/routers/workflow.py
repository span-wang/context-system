from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from deps import get_db
from exporters.xiaohongshu import build_publish_package_from_markdown, render_publish_package
from routers.generate import _create_job, _ensure_context_size, _initial_context, _run_generation, review_generation
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
    return get_db().create_topic(topic, actor=topic.owner, note="选题入库")


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
            note="从选题发起内容生成",
            actor=topic.owner,
        ),
        event_type="generation_started",
    )
    asyncio.create_task(_run_topic_generation(topic_id, job.id, generation_request))
    return WorkflowGenerateResponse(topic=updated, job_id=job.id)


@router.post("/topics/{topic_id}/review", response_model=WorkflowTopic)
async def review_topic(topic_id: str, request: ReviewRequest | None = None) -> WorkflowTopic:
    topic = _get_topic_or_404(topic_id)
    if not topic.generation_job_id:
        raise HTTPException(status_code=409, detail="topic has no generation job")
    _update_topic_or_404(
        topic_id,
        WorkflowTopicPatch(status="reviewing", review_status="reviewing", note="发起内容审查", actor=topic.owner),
        event_type="review_started",
    )
    job = await review_generation(topic.generation_job_id, request)
    review_passed = bool(job.review and job.review.pass_overall)
    return _update_topic_or_404(
        topic_id,
        WorkflowTopicPatch(
            status="awaiting_confirm" if review_passed else "needs_changes",
            review_status="passed" if review_passed else "needs_changes",
            note="内容审查完成",
            actor=topic.owner,
        ),
        event_type="review_completed",
    )


@router.post("/topics/{topic_id}/confirm", response_model=WorkflowTopic)
def confirm_topic(topic_id: str, request: WorkflowConfirmRequest) -> WorkflowTopic:
    topic = _get_topic_or_404(topic_id)
    return _update_topic_or_404(
        topic_id,
        WorkflowTopicPatch(
            status="approved",
            confirmed_by=request.confirmed_by or topic.owner,
            confirmed_at=datetime.utcnow(),
            note=request.note or "人工确认通过",
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
                note=request.note or "导出发布包",
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
    await _run_generation(job_id, request)
    job = get_db().get_job(job_id)
    if not job:
        return
    topic = get_db().get_topic(topic_id)
    if not topic or topic.generation_job_id != job_id:
        return
    if job.status == "done" and job.result:
        status = "generated"
        note = "生成完成，等待审查"
        event_type = "generation_completed"
    else:
        status = "needs_changes"
        note = job.error or "生成失败"
        event_type = "generation_failed"
    get_db().update_topic(
        topic_id,
        WorkflowTopicPatch(status=status, note=note, actor=topic.owner),
        event_type=event_type,
    )


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
        f"选题：{topic.title}",
        f"发布渠道：{topic.publish_channel}",
    ]
    if topic.brief:
        parts.append(f"选题说明：{topic.brief}")
    if topic.content_goal:
        parts.append(f"内容目标：{topic.content_goal}")
    if topic.audience:
        parts.append(f"目标读者：{topic.audience}")
    if extra_notes:
        parts.append(f"补充要求：{extra_notes}")
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
        "## 发布信息",
        f"- 选题ID：{topic.id}",
        f"- 责任人：{topic.owner or '未指定'}",
        f"- 发布渠道：{topic.publish_channel}",
        f"- 计划日期：{topic.scheduled_date or '未排期'}",
        f"- 当前状态：{topic.status}",
        f"- 审核状态：{topic.review_status}",
        f"- 生成任务：{topic.generation_job_id or '未绑定'}",
        "",
        "## 素材引用",
    ]
    if topic.material_file_ids:
        for index, file_id in enumerate(topic.material_file_ids, start=1):
            source = get_db().get_library_file(file_id)
            label = source.source_title or source.filename if source else file_id
            lines.append(f"- [{index}] {label}（{file_id}）")
    elif topic.ragflow_dataset_ids:
        lines.extend(f"- RAGFlow dataset：{dataset_id}" for dataset_id in topic.ragflow_dataset_ids)
    else:
        lines.append("- 未绑定素材")

    lines.extend(
        [
            "",
            "## 审查结论",
            f"- 结论：{('通过' if review.pass_overall else '需修改') if review else '未审查'}",
        ]
    )
    if review:
        lines.append(f"- 审查模式：{review.mode}")
        lines.append(f"- 问题数：{len(review.issues)}")
        if review.suggestions:
            lines.append("- 建议：")
            lines.extend(f"  - {item}" for item in review.suggestions)

    lines.extend(
        [
            "",
            "## 小红书发布包",
            "",
            render_publish_package(publish_package, fallback_title=job.result.title).strip(),
            "",
            "## 版本记录",
        ]
    )
    for event in events:
        lines.append(f"- v{event.version} {event.created_at.isoformat()} {event.event_type} {event.actor or ''} {event.note or ''}".rstrip())
    return "\n".join(lines).strip() + "\n"
