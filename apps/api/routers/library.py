from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from deps import get_library_service
from library.parse_jobs import get_library_parse_job, start_library_parse_job
from library.parse_options import (
    DEFAULT_PARSE_OUTPUT_FORMAT,
    DEFAULT_PARSE_PRESET,
    ParseOutputFormat,
    ParsePreset,
    build_document_parse_options,
)
from schemas.library import (
    LibraryFile,
    LibraryFilePatch,
    LibraryFilePreview,
    LibraryParseJobResponse,
    LibraryParseJobStatus,
    LibraryParseMode,
    LibraryReparseResponse,
)


router = APIRouter(prefix="/api/library", tags=["library"])


@router.post("/upload", response_model=list[LibraryFile])
async def upload_files(
    files: list[UploadFile] = File(...),
    batch_meta: str = Form(...),
    per_file_overrides: str | None = Form(None),
) -> list[LibraryFile]:
    service = get_library_service()
    return await service.ingest_batch(files, batch_meta, per_file_overrides)


@router.get("/files", response_model=list[LibraryFile])
def list_files(
    subject: str | None = Query(None),
    category: str | None = Query(None),
    source_type: str | None = Query(None),
    search: str | None = Query(None),
) -> list[LibraryFile]:
    return get_library_service().list_files(subject, category, source_type, search)


@router.get("/files/{file_id}", response_model=LibraryFile)
def get_file(file_id: str) -> LibraryFile:
    return get_library_service().get_file(file_id)


@router.patch("/files/{file_id}", response_model=LibraryFile)
def update_file(file_id: str, patch: LibraryFilePatch) -> LibraryFile:
    return get_library_service().update_file(file_id, patch)


@router.delete("/files/{file_id}")
async def delete_file(file_id: str) -> dict:
    await get_library_service().delete_file(file_id)
    return {"ok": True}


@router.get("/files/{file_id}/preview", response_model=LibraryFilePreview)
async def preview_file(
    file_id: str,
    max_chars: int = Query(4000, ge=1, le=500_000),
    compare: bool = Query(False),
    preset: ParsePreset = Query(DEFAULT_PARSE_PRESET),
    output_format: ParseOutputFormat = Query(DEFAULT_PARSE_OUTPUT_FORMAT),
    raw_ocr_mode: bool | None = Query(None),
    preserve_pdf_image_content: bool | None = Query(None),
    force_ocr: bool | None = Query(None),
    render_dpi: int | None = Query(None, ge=96, le=360),
    crop_header_ratio: float | None = Query(None, ge=0.0, le=0.2),
    crop_footer_ratio: float | None = Query(None, ge=0.0, le=0.2),
    trim_margins: bool | None = Query(None),
    remove_repeated_lines: bool | None = Query(None),
    watermark_detection: bool | None = Query(None),
    enable_formula_recognition: bool | None = Query(None),
    pdf_page_chunk_size: int | None = Query(None, ge=1, le=50),
) -> LibraryFilePreview:
    options = build_document_parse_options(
        preset=preset,
        output_format=output_format,
        raw_ocr_mode=raw_ocr_mode,
        preserve_pdf_image_content=preserve_pdf_image_content,
        force_ocr=force_ocr,
        render_dpi=render_dpi,
        crop_header_ratio=crop_header_ratio,
        crop_footer_ratio=crop_footer_ratio,
        trim_margins=trim_margins,
        remove_repeated_lines=remove_repeated_lines,
        watermark_detection=watermark_detection,
        enable_formula_recognition=enable_formula_recognition,
        pdf_page_chunk_size=pdf_page_chunk_size,
    )
    try:
        return await get_library_service().preview(file_id, max_chars=max_chars, options=options, compare=compare)
    except HTTPException:
        raise
    except Exception as exc:
        _raise_library_internal_error("素材库解析预览", exc)


@router.post("/files/{file_id}/parse-jobs", response_model=LibraryParseJobResponse)
def start_parse_file_job(
    file_id: str,
    mode: LibraryParseMode = Query("preview"),
    max_chars: int = Query(4000, ge=1, le=500_000),
    preset: ParsePreset = Query(DEFAULT_PARSE_PRESET),
    output_format: ParseOutputFormat = Query(DEFAULT_PARSE_OUTPUT_FORMAT),
    raw_ocr_mode: bool | None = Query(None),
    preserve_pdf_image_content: bool | None = Query(None),
    force_ocr: bool | None = Query(None),
    render_dpi: int | None = Query(None, ge=96, le=360),
    crop_header_ratio: float | None = Query(None, ge=0.0, le=0.2),
    crop_footer_ratio: float | None = Query(None, ge=0.0, le=0.2),
    trim_margins: bool | None = Query(None),
    remove_repeated_lines: bool | None = Query(None),
    watermark_detection: bool | None = Query(None),
    enable_formula_recognition: bool | None = Query(None),
    pdf_page_chunk_size: int | None = Query(None, ge=1, le=50),
) -> LibraryParseJobResponse:
    options = build_document_parse_options(
        preset=preset,
        output_format=output_format,
        raw_ocr_mode=raw_ocr_mode,
        preserve_pdf_image_content=preserve_pdf_image_content,
        force_ocr=force_ocr,
        render_dpi=render_dpi,
        crop_header_ratio=crop_header_ratio,
        crop_footer_ratio=crop_footer_ratio,
        trim_margins=trim_margins,
        remove_repeated_lines=remove_repeated_lines,
        watermark_detection=watermark_detection,
        enable_formula_recognition=enable_formula_recognition,
        pdf_page_chunk_size=pdf_page_chunk_size,
    )
    job = start_library_parse_job(file_id, mode=mode, max_chars=max_chars, options=options)
    return LibraryParseJobResponse(
        job_id=job.id,
        file_id=file_id,
        mode=mode,
        status=job.status,
        progress=job.progress,
    )


@router.get("/parse-jobs/{job_id}", response_model=LibraryParseJobStatus)
def get_parse_file_job(job_id: int) -> LibraryParseJobStatus:
    return LibraryParseJobStatus.model_validate(get_library_parse_job(job_id))


@router.post("/files/{file_id}/reparse", response_model=LibraryReparseResponse)
async def reparse_file(
    file_id: str,
    max_chars: int = Query(4000, ge=1, le=500_000),
    preset: ParsePreset = Query(DEFAULT_PARSE_PRESET),
    output_format: ParseOutputFormat = Query(DEFAULT_PARSE_OUTPUT_FORMAT),
    raw_ocr_mode: bool | None = Query(None),
    preserve_pdf_image_content: bool | None = Query(None),
    force_ocr: bool | None = Query(None),
    render_dpi: int | None = Query(None, ge=96, le=360),
    crop_header_ratio: float | None = Query(None, ge=0.0, le=0.2),
    crop_footer_ratio: float | None = Query(None, ge=0.0, le=0.2),
    trim_margins: bool | None = Query(None),
    remove_repeated_lines: bool | None = Query(None),
    watermark_detection: bool | None = Query(None),
    enable_formula_recognition: bool | None = Query(None),
    pdf_page_chunk_size: int | None = Query(None, ge=1, le=50),
) -> LibraryReparseResponse:
    options = build_document_parse_options(
        preset=preset,
        output_format=output_format,
        raw_ocr_mode=raw_ocr_mode,
        preserve_pdf_image_content=preserve_pdf_image_content,
        force_ocr=force_ocr,
        render_dpi=render_dpi,
        crop_header_ratio=crop_header_ratio,
        crop_footer_ratio=crop_footer_ratio,
        trim_margins=trim_margins,
        remove_repeated_lines=remove_repeated_lines,
        watermark_detection=watermark_detection,
        enable_formula_recognition=enable_formula_recognition,
        pdf_page_chunk_size=pdf_page_chunk_size,
    )
    try:
        return await get_library_service().reparse(file_id, max_chars=max_chars, options=options)
    except HTTPException:
        raise
    except Exception as exc:
        _raise_library_internal_error("素材库重新解析入库", exc)


def _raise_library_internal_error(action: str, exc: Exception) -> None:
    message = str(exc).strip() or exc.__class__.__name__
    if len(message) > 800:
        message = f"{message[:800]}..."
    raise HTTPException(
        status_code=500,
        detail=f"{action}失败：{exc.__class__.__name__}: {message}",
    ) from exc
