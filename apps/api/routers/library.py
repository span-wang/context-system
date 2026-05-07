from __future__ import annotations

from fastapi import APIRouter, File, Form, Query, UploadFile

from deps import get_library_service
from library.parse_options import DocumentParseOptions, ParsePreset
from schemas.library import LibraryFile, LibraryFilePatch, LibraryFilePreview


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
    preset: ParsePreset = Query("auto"),
    force_ocr: bool | None = Query(None),
    render_dpi: int | None = Query(None, ge=96, le=300),
    crop_header_ratio: float | None = Query(None, ge=0.0, le=0.2),
    crop_footer_ratio: float | None = Query(None, ge=0.0, le=0.2),
    trim_margins: bool | None = Query(None),
    remove_repeated_lines: bool | None = Query(None),
    watermark_detection: bool | None = Query(None),
    enable_formula_recognition: bool | None = Query(None),
) -> LibraryFilePreview:
    options = DocumentParseOptions(
        preset=preset,
        force_ocr=force_ocr,
        render_dpi=render_dpi,
        crop_header_ratio=crop_header_ratio,
        crop_footer_ratio=crop_footer_ratio,
        trim_margins=trim_margins,
        remove_repeated_lines=remove_repeated_lines,
        watermark_detection=watermark_detection,
        enable_formula_recognition=enable_formula_recognition,
    )
    return await get_library_service().preview(file_id, max_chars=max_chars, options=options)
