from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse, StreamingResponse

from deps import get_db, get_library_service, get_ragflow_provider
from background import enqueue_background_task, register_task_handler
from exporters.markdown import export_markdown
from exporters.xiaohongshu import build_publish_package_from_markdown
from generators import get_generator
from generators.llm import LLMContentGenerator
from llm.providers import get_llm_provider
from library.token_counter import estimate_sources_tokens
from review.pipeline import review_result
from schemas.context import ContentType, GenerationContext
from schemas.generation import GenerationJob, GenerationRequest
from schemas.library import FileMetadata
from schemas.review import ReviewItemReplaceRequest, ReviewItemUpdateRequest, ReviewRequest
from settings import get_settings, normalize_subject_name


router = APIRouter(prefix="/api/generate", tags=["generate"])


@router.post("")
async def create_generation(request: GenerationRequest) -> dict:
    request = _normalize_generation_request(request)
    context = await _initial_context(request)
    _ensure_context_size(context)
    job = _create_job(context)
    _enqueue_generation_job(job.id, request)
    return {"job_id": job.id}


@router.post("/multipart")
async def create_generation_multipart(
    subject: str = Form(...),
    content_type: ContentType = Form(...),
    category: str | None = Form(None),
    chapter: str | None = Form(None),
    options: str = Form("{}"),
    user_notes: str | None = Form(None),
    library_file_ids: str = Form("[]"),
    save_uploads_to_library: bool = Form(False),
    batch_meta: str | None = Form(None),
    new_uploads: list[UploadFile] | None = File(None),
) -> dict:
    subject = _normalize_subject_or_422(subject)
    context = await _multipart_context(
        subject=subject,
        category=category,
        chapter=chapter,
        content_type=content_type,
        options=_loads_object(options, "options"),
        user_notes=user_notes,
        library_file_ids=_loads_list(library_file_ids, "library_file_ids"),
        save_uploads_to_library=save_uploads_to_library,
        batch_meta=batch_meta,
        new_uploads=new_uploads or [],
    )
    _ensure_context_size(context)
    job = _create_job(context)
    _enqueue_generation_job(job.id, None)
    return {"job_id": job.id}


@router.get("/{job_id}")
def get_generation(job_id: str) -> GenerationJob:
    job = get_db().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="generation job not found")
    return job


@router.get("/{job_id}/stream")
async def stream_generation(job_id: str) -> StreamingResponse:
    async def events():
        previous = None
        while True:
            job = get_db().get_job(job_id)
            if not job:
                yield 'event: error\ndata: {"detail":"generation job not found"}\n\n'
                break
            payload = {
                "id": job.id,
                "status": job.status,
                "error": job.error,
                "has_result": job.result is not None,
                "has_review": job.review is not None,
            }
            current = json.dumps(payload, ensure_ascii=False)
            if current != previous:
                yield f"event: status\ndata: {current}\n\n"
                previous = current
            if job.status in {"done", "failed"}:
                data = json.dumps(job.model_dump(mode="json"), ensure_ascii=False)
                yield f"event: done\ndata: {data}\n\n"
                break
            await asyncio.sleep(0.8)

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/{job_id}/retry")
async def retry_generation(job_id: str) -> dict:
    job = get_db().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="generation job not found")
    request = GenerationRequest(
        mode=job.context.mode,
        subject=job.context.subject,
        category=job.context.category,
        chapter=job.context.chapter,
        content_type=job.context.content_type,
        options=job.context.options,
        user_notes=job.context.user_notes,
        library_file_ids=[source.file_id for source in job.context.sources if source.file_id],
    )
    job.status = "pending"
    job.error = None
    job.result = None
    job.review = None
    get_db().update_job(job)
    _enqueue_generation_job(job.id, request)
    return {"job_id": job.id}


@router.post("/{job_id}/review", response_model=GenerationJob)
async def review_generation(job_id: str, request: ReviewRequest | None = None) -> GenerationJob:
    job = get_db().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="generation job not found")
    if not job.result:
        raise HTTPException(status_code=409, detail="generation result is not ready")
    if job.status == "reviewing":
        raise HTTPException(status_code=409, detail="content review is already running")

    job.status = "reviewing"
    job.error = None
    get_db().update_job(job)
    _enqueue_review_job(job.id, request)
    return job


async def run_review_job(job_id: str, request: ReviewRequest | None = None) -> GenerationJob:
    job = get_db().get_job(job_id)
    if not job:
        raise RuntimeError("generation job not found")
    if not job.result:
        raise RuntimeError("generation result is not ready")
    try:
        settings = get_settings()
        endpoint = settings.llm.reviewer
        llm_provider = None
        if endpoint.provider != "local_template":
            llm_provider = get_llm_provider(endpoint, target="reviewer")
        job.review = await review_result(
            job.result,
            job.context,
            settings.review,
            mode=request.mode if request else "hybrid",
            llm_provider=llm_provider,
            llm_max_tokens=endpoint.max_tokens,
        )
        job.status = "done"
        get_db().update_job(job)
        return job
    except Exception as exc:
        job.status = "done"
        job.error = str(exc)
        get_db().update_job(job)
        raise RuntimeError(f"content review failed: {exc}") from exc


@router.patch("/{job_id}/review/items/{item_id}", response_model=GenerationJob)
def update_review_item(job_id: str, item_id: str, request: ReviewItemUpdateRequest) -> GenerationJob:
    job = _get_reviewable_job(job_id)
    item = _find_review_item(job, item_id)
    if request.status is not None:
        item.status = request.status
    if request.original_text is not None:
        item.original_text = request.original_text if request.original_text.strip() else None
    if request.replacement_text is not None:
        item.replacement_text = request.replacement_text if request.replacement_text.strip() else None
    get_db().update_job(job)
    return job


@router.post("/{job_id}/review/items/{item_id}/replace", response_model=GenerationJob)
def replace_review_item(job_id: str, item_id: str, request: ReviewItemReplaceRequest) -> GenerationJob:
    job = _get_reviewable_job(job_id)
    if not job.result:
        raise HTTPException(status_code=409, detail="generation result is not ready")
    item = _find_review_item(job, item_id)
    original_text = (request.original_text if request.original_text is not None else item.original_text) or ""
    replacement_text = (request.replacement_text if request.replacement_text is not None else item.replacement_text) or ""
    if not original_text.strip():
        raise HTTPException(status_code=422, detail="original_text is required before replacing")
    body_slice = _body_slice(job.result.raw_markdown)
    matches = _find_markdown_matches(body_slice["body"], original_text)
    if not matches:
        raise HTTPException(status_code=409, detail="original_text was not found in the current Markdown")
    matched_original = matches[0]

    item.original_text = matched_original
    item.replacement_text = replacement_text
    if request.replace_all:
        replace_count = len(matches)
        updated_body = _replace_matched_segments(body_slice["body"], matches, replacement_text)
        job.result.raw_markdown = _merge_body_slice(job.result.raw_markdown, body_slice, updated_body)
        if job.result.publish_package:
            publish_matches = _find_markdown_matches(job.result.publish_package.body, original_text)
            if publish_matches:
                job.result.publish_package.body = _replace_matched_segments(
                    job.result.publish_package.body,
                    publish_matches,
                    replacement_text,
                )
    else:
        replace_count = 1
        updated_body = _replace_matched_segments(body_slice["body"], [matched_original], replacement_text)
        job.result.raw_markdown = _merge_body_slice(job.result.raw_markdown, body_slice, updated_body)
        if job.result.publish_package:
            publish_matches = _find_markdown_matches(job.result.publish_package.body, original_text)
            if publish_matches:
                job.result.publish_package.body = _replace_matched_segments(
                    job.result.publish_package.body,
                    [publish_matches[0]],
                    replacement_text,
                )
    if not job.result.publish_package:
        job.result.publish_package = build_publish_package_from_markdown(
            title=job.result.title,
            markdown=job.result.raw_markdown,
            context=job.context,
            sections=job.result.sections,
            unverified=job.result.unverified,
        )
    item.replace_count += replace_count
    item.status = "replaced"
    get_db().update_job(job)
    return job


@router.get("/{job_id}/export")
def export_generation(job_id: str, format: str = Query("md")) -> PlainTextResponse:
    job = get_db().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="generation job not found")
    if format != "md":
        raise HTTPException(status_code=422, detail="Only md export is implemented in the MVP.")
    filename = f"{job.result.title if job.result else job.id}.md".replace("/", "_")
    return PlainTextResponse(
        export_markdown(job),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        media_type="text/markdown; charset=utf-8",
    )


async def _initial_context(request: GenerationRequest) -> GenerationContext:
    subject = _normalize_subject_or_422(request.subject)
    sources = []
    if request.mode == "direct":
        service = get_library_service()
        for file_id in request.library_file_ids:
            sources.append(await service.to_context_source(file_id))
    return GenerationContext(
        mode=request.mode,
        subject=subject,
        category=request.category,
        chapter=request.chapter,
        content_type=request.content_type,
        options=request.options,
        sources=sources,
        user_notes=request.user_notes,
        has_authoritative_source=any(source.authority in {"high", "medium"} for source in sources),
    )


async def _multipart_context(
    subject: str,
    category: str | None,
    chapter: str | None,
    content_type: ContentType,
    options: dict,
    user_notes: str | None,
    library_file_ids: list[str],
    save_uploads_to_library: bool,
    batch_meta: str | None,
    new_uploads: list[UploadFile],
) -> GenerationContext:
    service = get_library_service()
    sources = []
    for file_id in library_file_ids:
        sources.append(await service.to_context_source(file_id))

    upload_meta = _metadata_from_form(batch_meta, subject, category, chapter)
    for upload in new_uploads:
        sources.append(
            await service.upload_to_context_source(
                upload=upload,
                metadata=upload_meta,
                save=save_uploads_to_library,
            )
        )

    return GenerationContext(
        mode="direct",
        subject=subject,
        category=category,
        chapter=chapter,
        content_type=content_type,
        options=options,
        sources=sources,
        user_notes=user_notes,
        has_authoritative_source=any(source.authority in {"high", "medium"} for source in sources),
    )


async def _run_generation(job_id: str, request: GenerationRequest | None) -> None:
    db = get_db()
    job = db.get_job(job_id)
    if not job:
        return
    try:
        if request and request.mode == "ragflow":
            job.status = "retrieving"
            db.update_job(job)
            query = " ".join(
                item
                for item in [
                    request.subject,
                    request.category,
                    request.chapter,
                    request.content_type,
                ]
                if item
            )
            filters = {
                "subject": request.subject,
                "category": request.category,
                "chapter": request.chapter,
            }
            sources = await get_ragflow_provider().retrieve(query, request.ragflow_dataset_ids, filters)
            job.context.sources = sources
            job.context.has_authoritative_source = any(
                source.authority in {"high", "medium"} for source in sources
            )

        job.status = "generating"
        db.update_job(job)
        result = await _generate_result(job.context)
        job.result = result
        job.status = "done"
        db.update_job(job)
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        db.update_job(job)
        raise


async def _generate_result(context: GenerationContext):
    endpoint = get_settings().llm.generator
    if endpoint.provider == "local_template":
        return await get_generator(context.content_type).generate(context)
    provider = get_llm_provider(endpoint, target="generator")
    return await LLMContentGenerator(provider, endpoint).generate(context)


def _create_job(context: GenerationContext) -> GenerationJob:
    job = GenerationJob(
        id=str(uuid4()),
        context=context,
        status="pending",
        created_at=datetime.utcnow(),
    )
    get_db().create_job(job)
    return job


def _enqueue_generation_job(job_id: str, request: GenerationRequest | None) -> None:
    payload = {
        "job_id": job_id,
        "request": request.model_dump(mode="json") if request else None,
    }
    enqueue_background_task("generation", payload)


def _enqueue_review_job(job_id: str, request: ReviewRequest | None = None) -> None:
    payload = {
        "job_id": job_id,
        "request": request.model_dump(mode="json") if request else None,
    }
    enqueue_background_task("review", payload)


async def _handle_generation_task(payload: dict) -> None:
    request_data = payload.get("request")
    request = GenerationRequest.model_validate(request_data) if request_data else None
    await _run_generation(str(payload["job_id"]), request)


async def _handle_review_task(payload: dict) -> None:
    request_data = payload.get("request")
    request = ReviewRequest.model_validate(request_data) if request_data else None
    await run_review_job(str(payload["job_id"]), request)


register_task_handler("generation", _handle_generation_task)
register_task_handler("review", _handle_review_task)


def _get_reviewable_job(job_id: str) -> GenerationJob:
    job = get_db().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="generation job not found")
    if not job.review:
        raise HTTPException(status_code=409, detail="content review is not ready")
    return job


def _find_review_item(job: GenerationJob, item_id: str):
    if not job.review:
        raise HTTPException(status_code=409, detail="content review is not ready")
    for item in job.review.items:
        if item.id == item_id:
            return item
    raise HTTPException(status_code=404, detail="review item not found")


def _ensure_context_size(context: GenerationContext) -> None:
    layout_prompt = str(context.options.get("layout_prompt") or "").strip()
    if layout_prompt and _layout_prompt_is_self_contained(layout_prompt):
        total_tokens = estimate_sources_tokens([], layout_prompt)
    else:
        total_tokens = estimate_sources_tokens(
            [source.text for source in context.sources],
            "\n".join(item for item in [context.user_notes, layout_prompt] if item),
        )
    limit = get_settings().app.context_token_limit
    if total_tokens > limit:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "context_too_large",
                "tokens": total_tokens,
                "limit": limit,
                "suggestion": "Reduce source files, crop PDFs by chapter, or switch to RAGFlow mode.",
            },
        )


def _layout_prompt_is_self_contained(layout_prompt: str) -> bool:
    return any(
        marker in layout_prompt
        for marker in (
            "[Library Sources]",
            "[New Uploads]",
            "[Source Content]",
            "Source content:",
        )
    )


def _metadata_from_form(
    batch_meta: str | None,
    subject: str,
    category: str | None,
    chapter: str | None,
) -> FileMetadata:
    raw = _loads_object(batch_meta or "{}", "batch_meta")
    raw["subject"] = _normalize_subject_or_422(subject)
    raw.setdefault("category", category)
    raw.setdefault("chapter", chapter)
    raw.setdefault("source_type", "other")
    raw.setdefault("source_authority", "medium")
    raw.setdefault("source_title", "")
    raw.setdefault("tags", [])
    return FileMetadata.model_validate(raw)


def _normalize_generation_request(request: GenerationRequest) -> GenerationRequest:
    return request.model_copy(update={"subject": _normalize_subject_or_422(request.subject)})


def _normalize_subject_or_422(subject: str) -> str:
    normalized = normalize_subject_name(subject)
    if not normalized:
        raise HTTPException(status_code=422, detail=f"unknown subject: {subject}")
    return normalized


def _loads_object(raw: str, field: str) -> dict:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"invalid {field}: {exc}") from exc
    if not isinstance(value, dict):
        raise HTTPException(status_code=422, detail=f"{field} must be an object")
    return value


def _loads_list(raw: str, field: str) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        value = [item.strip() for item in raw.split(",") if item.strip()]
    if not isinstance(value, list):
        raise HTTPException(status_code=422, detail=f"{field} must be a list")
    return [str(item) for item in value if item]


def _find_markdown_matches(markdown: str, original_text: str) -> list[str]:
    if not markdown or not original_text:
        return []
    if original_text in markdown:
        return [original_text]

    normalized_markdown, markdown_positions = _normalize_for_match(markdown)
    normalized_original, _ = _normalize_for_match(original_text)
    if not normalized_original:
        return []

    matches: list[str] = []
    seen: set[tuple[int, int]] = set()
    start = 0
    while True:
        index = normalized_markdown.find(normalized_original, start)
        if index < 0:
            break
        start_pos = markdown_positions[index]
        end_index = index + len(normalized_original) - 1
        end_pos = markdown_positions[end_index] + 1
        key = (start_pos, end_pos)
        if key not in seen:
            seen.add(key)
            matches.append(markdown[start_pos:end_pos])
        start = index + 1
    return matches


def _replace_matched_segments(text: str, targets: list[str], replacement: str) -> str:
    updated = text
    for target in targets:
        updated = updated.replace(target, replacement, 1)
    return updated


def _body_slice(markdown: str) -> dict[str, int | str]:
    if not markdown:
        return {"body": "", "start": 0, "end": 0}

    body_section_pattern = re.compile(r"^\s{0,3}#{1,6}\s*(?:正文|发布正文)\s*$", flags=re.MULTILINE)
    non_body_section_pattern = re.compile(
        r"^\s{0,3}#{1,6}\s*(?:"
        r"笔记标题(?:\s*5\s*个)?备选|"
        r"标题(?:备选|建议)?|"
        r"封面文案|"
        r"轮播图逐页文案|"
        r"轮播图|"
        r"标签建议|"
        r"评论区引导|"
        r"评论引导"
        r")\s*$",
        flags=re.MULTILINE,
    )

    body_match = body_section_pattern.search(markdown)
    if body_match:
        start = body_match.end()
        next_non_body = non_body_section_pattern.search(markdown, start)
        end = next_non_body.start() if next_non_body else len(markdown)
        return {"body": markdown[start:end].strip(), "start": start, "end": end}

    first_non_body = non_body_section_pattern.search(markdown)
    end = first_non_body.start() if first_non_body else len(markdown)
    return {"body": markdown[:end].strip(), "start": 0, "end": end}


def _merge_body_slice(markdown: str, body_slice: dict[str, int | str], new_body: str) -> str:
    start = int(body_slice["start"])
    end = int(body_slice["end"])

    if start == 0:
        suffix = markdown[end:]
        return f"{new_body}{suffix}"

    raw_segment = markdown[start:end]
    leading_len = len(raw_segment) - len(raw_segment.lstrip())
    trailing_len = len(raw_segment) - len(raw_segment.rstrip())
    leading = raw_segment[:leading_len]
    trailing = raw_segment[len(raw_segment) - trailing_len :] if trailing_len else ""
    replacement = f"{leading}{new_body}{trailing}"
    return f"{markdown[:start]}{replacement}{markdown[end:]}"


def _normalize_for_match(text: str) -> tuple[str, list[int]]:
    normalized_chars: list[str] = []
    positions: list[int] = []
    punctuation_map = {
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "（": "(",
        "）": ")",
        "：": ":",
        "，": ",",
        "；": ";",
        "。": ".",
        "、": ",",
        "＋": "+",
        "－": "-",
        "—": "-",
        "–": "-",
        "−": "-",
        "＝": "=",
        "…": "...",
        "·": ".",
    }
    for index, char in enumerate(text):
        if char.isspace():
            continue
        if char in {"*", "`", "_"}:
            continue
        normalized = punctuation_map.get(char, char)
        normalized = unicodedata.normalize("NFKC", normalized)
        if normalized.isspace():
            continue
        for normalized_char in normalized:
            if normalized_char.isspace():
                continue
            normalized_chars.append(normalized_char)
            positions.append(index)
    return "".join(normalized_chars), positions
