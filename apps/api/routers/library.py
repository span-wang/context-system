from __future__ import annotations

from fastapi import APIRouter, File, Form, Query, UploadFile

from deps import get_library_service
from schemas.library import LibraryFile, LibraryFilePatch


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


@router.get("/files/{file_id}/preview")
async def preview_file(file_id: str) -> dict:
    return await get_library_service().preview(file_id)

