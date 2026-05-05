from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from library.parser import parse_bytes
from library.token_counter import estimate_tokens
from schemas.context import ContextSource
from schemas.library import FileMetadata, LibraryFile, LibraryFilePatch
from settings import normalize_subject_name
from storage.db import Database
from storage.local import LocalFSStorage


DEFAULT_PREVIEW_CHARS = 4_000
MAX_PREVIEW_CHARS = 500_000
PLACEHOLDER_SOURCE_TITLES = {"批量上传资料", "uploaded source"}


class LibraryService:
    def __init__(self, db: Database, storage: LocalFSStorage) -> None:
        self.db = db
        self.storage = storage
        self.cache_root = storage.root / "cache" / "parsed"
        self.cache_root.mkdir(parents=True, exist_ok=True)

    async def ingest_upload(self, upload: UploadFile, metadata: FileMetadata) -> LibraryFile:
        metadata = self._normalize_metadata(metadata)
        data = await upload.read()
        sha256 = hashlib.sha256(data).hexdigest()
        existing = self.db.get_library_by_sha(sha256)
        if existing:
            return self._with_display_title(existing)
        suffix = Path(upload.filename or "upload.bin").suffix.lower()
        yyyymm = datetime.utcnow().strftime("%Y%m")
        storage_path = f"library/{yyyymm}/{sha256}{suffix}"
        await self.storage.put(storage_path, data)
        filename = upload.filename or f"{sha256}{suffix}"
        source_title = self._display_source_title(metadata.source_title, filename)
        file = LibraryFile(
            id=str(uuid4()),
            sha256=sha256,
            filename=filename,
            size=len(data),
            mime=upload.content_type or "application/octet-stream",
            storage_path=storage_path,
            subject=metadata.subject,
            category=metadata.category,
            chapter=metadata.chapter,
            source_type=metadata.source_type,
            source_authority=metadata.source_authority,
            source_title=source_title,
            source_publisher=metadata.source_publisher,
            source_code=metadata.source_code,
            source_version=metadata.source_version,
            year=metadata.year,
            tags=metadata.tags,
            created_at=datetime.utcnow(),
        )
        return self._with_display_title(self.db.insert_library_file(file))

    async def ingest_batch(
        self,
        uploads: list[UploadFile],
        batch_meta_json: str | None,
        per_file_overrides_json: str | None,
    ) -> list[LibraryFile]:
        batch_meta = self._metadata_from_json(batch_meta_json)
        overrides = json.loads(per_file_overrides_json or "{}")
        files: list[LibraryFile] = []
        for upload in uploads:
            file_override = overrides.get(upload.filename or "", {})
            data = batch_meta.model_dump()
            data.update(file_override)
            files.append(await self.ingest_upload(upload, FileMetadata.model_validate(data)))
        return files

    def list_files(
        self,
        subject: str | None = None,
        category: str | None = None,
        source_type: str | None = None,
        search: str | None = None,
    ) -> list[LibraryFile]:
        if subject:
            subject = self._normalize_subject_or_422(subject)
        return [self._with_display_title(file) for file in self.db.list_library_files(subject, category, source_type, search)]

    def get_file(self, file_id: str) -> LibraryFile:
        file = self.db.get_library_file(file_id)
        if not file:
            raise HTTPException(status_code=404, detail="library file not found")
        return self._with_display_title(file)

    def update_file(self, file_id: str, patch: LibraryFilePatch) -> LibraryFile:
        patch_updates = {}
        if patch.subject is not None:
            patch_updates["subject"] = self._normalize_subject_or_422(patch.subject)
        if patch.source_title is not None:
            patch_updates["source_title"] = self._sanitize_source_title(patch.source_title)
        if patch_updates:
            patch = patch.model_copy(update=patch_updates)
        file = self.db.update_library_file(file_id, patch)
        if not file:
            raise HTTPException(status_code=404, detail="library file not found")
        return self._with_display_title(file)

    async def delete_file(self, file_id: str) -> None:
        file = self.db.delete_library_file(file_id)
        if not file:
            raise HTTPException(status_code=404, detail="library file not found")
        await self.storage.delete(file.storage_path)
        cache_path = self.cache_root / f"{file.sha256}.txt"
        if cache_path.exists():
            cache_path.unlink()

    async def parse_and_cache(self, file: LibraryFile) -> str:
        if file.parsed_text:
            return file.parsed_text
        cache_path = self.cache_root / f"{file.sha256}.txt"
        if cache_path.exists():
            text = cache_path.read_text(encoding="utf-8")
        else:
            raw = await self.storage.get(file.storage_path)
            text = parse_bytes(raw, file.filename, file.mime)
            cache_path.write_text(text, encoding="utf-8")
        self.db.set_parsed_text(file.id, text, estimate_tokens(text))
        return text

    async def to_context_source(self, file_id: str) -> ContextSource:
        file = self.get_file(file_id)
        text = await self.parse_and_cache(file)
        self.db.mark_library_used(file_id)
        source_label = f"素材库:{file.source_title or file.filename}"
        if file.chapter:
            source_label += f"::{file.chapter}"
        return ContextSource(
            text=text,
            source_label=source_label,
            source_type=file.source_type,
            authority=file.source_authority,
            file_id=file.id,
        )

    async def upload_to_context_source(
        self,
        upload: UploadFile,
        metadata: FileMetadata,
        save: bool,
    ) -> ContextSource:
        if save:
            file = await self.ingest_upload(upload, metadata)
            return await self.to_context_source(file.id)

        data = await upload.read()
        filename = upload.filename or "upload"
        text = parse_bytes(data, filename, upload.content_type or "application/octet-stream")
        source_title = self._display_source_title(metadata.source_title, filename)
        label = f"本次上传:{source_title}"
        if metadata.chapter:
            label += f"::{metadata.chapter}"
        return ContextSource(
            text=text,
            source_label=label,
            source_type=metadata.source_type,
            authority=metadata.source_authority,
            file_id=None,
        )

    async def preview(self, file_id: str, max_chars: int = DEFAULT_PREVIEW_CHARS) -> dict:
        file = self.get_file(file_id)
        text = await self.parse_and_cache(file)
        preview_text = text
        if not text.strip():
            preview_text = (
                "[No text extracted. This file may be a low-quality scan, an image-only page, "
                "or OCR may not be installed correctly. The parser first extracts selectable "
                "PDF text and then falls back to OCR when needed.]"
            )
        max_chars = max(1, min(max_chars, MAX_PREVIEW_CHARS))
        return {
            "file_id": file.id,
            "filename": file.filename,
            "token_count": estimate_tokens(text),
            "text": preview_text[:max_chars],
            "truncated": len(preview_text) > max_chars,
        }
    def _metadata_from_json(self, raw: str | None) -> FileMetadata:
        if not raw:
            raise HTTPException(status_code=422, detail="batch_meta is required")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail=f"invalid batch_meta: {exc}") from exc
        return self._normalize_metadata(FileMetadata.model_validate(data))

    def _normalize_metadata(self, metadata: FileMetadata) -> FileMetadata:
        return metadata.model_copy(
            update={
                "subject": self._normalize_subject_or_422(metadata.subject),
                "source_title": self._sanitize_source_title(metadata.source_title),
            }
        )

    def _normalize_subject_or_422(self, subject: str) -> str:
        normalized = normalize_subject_name(subject)
        if not normalized:
            raise HTTPException(status_code=422, detail=f"unknown subject: {subject}")
        return normalized

    def _sanitize_source_title(self, source_title: str | None) -> str:
        title = (source_title or "").strip()
        return "" if title in PLACEHOLDER_SOURCE_TITLES else title

    def _display_source_title(self, source_title: str | None, filename: str | None) -> str:
        return self._sanitize_source_title(source_title) or Path(filename or "未命名资料").stem

    def _with_display_title(self, file: LibraryFile) -> LibraryFile:
        source_title = self._display_source_title(file.source_title, file.filename)
        if source_title == file.source_title:
            return file
        return file.model_copy(update={"source_title": source_title})
