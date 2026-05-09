from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Asset, ExamPaper
from app.services.papers import PaperService
from library.ocr_cleaner import clean_parsed_document
from library.ocr_cleaner import raw_document_snapshot
from library.parse_options import DocumentParseOptions
from library.parser import (
    ParseProgressCallback,
    ParsedDocument,
    deserialize_parsed_document,
    parse_document,
    serialize_parsed_document,
)
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
        files = self.db.list_library_files(subject, category, source_type, search)
        return [self._with_display_title(file) for file in files]

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
        self._delete_bound_exam_papers_by_sha(file.sha256)
        await self.storage.delete(file.storage_path)
        for pattern in (f"{file.sha256}.txt", f"{file.sha256}.json", f"{file.sha256}__*.txt", f"{file.sha256}__*.json"):
            for cache_path in self.cache_root.glob(pattern):
                if cache_path.exists():
                    cache_path.unlink()

    async def parse_and_cache(
        self,
        file: LibraryFile,
        options: DocumentParseOptions | None = None,
        *,
        preview: bool = False,
        force_reparse: bool = False,
        progress_callback: ParseProgressCallback | None = None,
    ) -> ParsedDocument:
        options = options or DocumentParseOptions()
        text_cache_path, structured_cache_path = self._parse_cache_paths(file, options, preview=preview)

        if not force_reparse and structured_cache_path.exists():
            parsed = deserialize_parsed_document(structured_cache_path.read_text(encoding="utf-8"))
            if parsed is not None:
                parsed = clean_parsed_document(parsed, force=True)
                if _is_stale_parse_cache(parsed):
                    structured_cache_path.unlink(missing_ok=True)
                    text_cache_path.unlink(missing_ok=True)
                else:
                    if not text_cache_path.exists():
                        text_cache_path.write_text(parsed.text, encoding="utf-8")
                    self._remember_parse_result(file.id, parsed, options=options, preview=preview)
                    if progress_callback is not None:
                        progress_callback("cache", 70, {"file_id": file.id, "cache_hit": True})
                    return parsed

        if not force_reparse and text_cache_path.exists():
            text = text_cache_path.read_text(encoding="utf-8")
            parsed = clean_parsed_document(ParsedDocument(text=text, markdown=text, provider="legacy_cache"), force=True)
            structured_cache_path.write_text(serialize_parsed_document(parsed), encoding="utf-8")
            self._remember_parse_result(file.id, parsed, options=options, preview=preview)
            if progress_callback is not None:
                progress_callback("cache", 70, {"file_id": file.id, "cache_hit": True})
            return parsed

        if progress_callback is not None:
            progress_callback("read_file", 10, {"file_id": file.id, "filename": file.filename})
        raw = await self.storage.get(file.storage_path)
        try:
            parsed = await asyncio.to_thread(
                parse_document,
                raw,
                file.filename,
                file.mime,
                options,
                progress_callback,
            )
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"文件解析失败：{exc}") from exc
        parsed = clean_parsed_document(parsed)
        text_cache_path.write_text(parsed.text, encoding="utf-8")
        structured_cache_path.write_text(serialize_parsed_document(parsed), encoding="utf-8")
        self._remember_parse_result(file.id, parsed, options=options, preview=preview)
        return parsed

    async def to_context_source(self, file_id: str, options: DocumentParseOptions | None = None) -> ContextSource:
        file = self.get_file(file_id)
        options = options or DocumentParseOptions()
        parsed = await self.parse_and_cache(file, options=options)
        self.db.mark_library_used(file_id)
        source_label = f"素材库:{file.source_title or file.filename}"
        if file.chapter:
            source_label += f"::{file.chapter}"
        return ContextSource(
            text=_selected_output(parsed, options),
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
        options: DocumentParseOptions | None = None,
    ) -> ContextSource:
        if save:
            file = await self.ingest_upload(upload, metadata)
            return await self.to_context_source(file.id, options=options)

        data = await upload.read()
        filename = upload.filename or "upload"
        try:
            parsed = await asyncio.to_thread(
                parse_document,
                data,
                filename,
                upload.content_type or "application/octet-stream",
                options,
            )
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"文件解析失败：{exc}") from exc
        parsed = clean_parsed_document(parsed)
        source_title = self._display_source_title(metadata.source_title, filename)
        label = f"本次上传:{source_title}"
        if metadata.chapter:
            label += f"::{metadata.chapter}"
        options = options or DocumentParseOptions()
        return ContextSource(
            text=_selected_output(parsed, options),
            source_label=label,
            source_type=metadata.source_type,
            authority=metadata.source_authority,
            file_id=None,
        )

    async def preview(
        self,
        file_id: str,
        max_chars: int = DEFAULT_PREVIEW_CHARS,
        options: DocumentParseOptions | None = None,
        *,
        compare: bool = False,
        progress_callback: ParseProgressCallback | None = None,
    ) -> dict:
        file = self.get_file(file_id)
        options = options or DocumentParseOptions()
        stored_result = self.db.get_latest_library_parse_result(file.id)
        if not compare and stored_result is not None and (
            stored_result.get("raw_text") is not None or stored_result.get("cleanup_report") is not None
        ):
            preview_markdown = str(stored_result.get("markdown") or stored_result.get("parsed_text") or "")
            preview_text = str(stored_result.get("parsed_text") or preview_markdown)
            preview_content = options.select_output(text=preview_text, markdown=preview_markdown)
            token_count = int(stored_result.get("token_count") or estimate_tokens(preview_markdown or preview_text))
            warnings = [str(item) for item in (stored_result.get("warnings") or []) if str(item).strip()]
            max_chars = max(1, min(max_chars, MAX_PREVIEW_CHARS))
            if progress_callback is not None:
                progress_callback("cache", 70, {"file_id": file.id, "cache_hit": True, "stored_result": True})
            return {
                "file_id": file.id,
                "filename": file.filename,
                "token_count": token_count,
                "provider": str(stored_result.get("provider") or "stored_parse"),
                "raw_text": str(stored_result.get("raw_text") or stored_result.get("parsed_text") or ""),
                "raw_markdown": str(stored_result.get("raw_markdown") or stored_result.get("markdown") or preview_markdown),
                "text": preview_text[:max_chars],
                "markdown": preview_markdown[:max_chars],
                "content": preview_content[:max_chars],
                "output_format": options.output_format,
                "table_count": 0,
                "warning_count": len(warnings),
                "warnings": warnings[:5],
                "truncated": len(preview_content) > max_chars,
                "parse_options": stored_result.get("parse_options") or {},
                "cleanup_report": stored_result.get("cleanup_report") or {},
                "cleanup_score": stored_result.get("cleanup_score"),
            }

        if compare:
            raw = await self.storage.get(file.storage_path)
            parsed = await asyncio.to_thread(
                parse_document,
                raw,
                file.filename,
                file.mime,
                options,
                progress_callback,
            )
        else:
            parsed = await self.parse_and_cache(
                file,
                options=options,
                preview=False,
                progress_callback=progress_callback,
            )

        selected_output = _selected_output(parsed, options)
        preview_text, preview_markdown, preview_content = _preview_payload(parsed, options)
        raw_snapshot = raw_document_snapshot(parsed)
        persisted_markdown = parsed.markdown or parsed.text
        token_count = estimate_tokens(persisted_markdown)
        max_chars = max(1, min(max_chars, MAX_PREVIEW_CHARS))
        return {
            "file_id": file.id,
            "filename": file.filename,
            "token_count": token_count,
            "provider": parsed.provider,
            "raw_text": raw_snapshot["raw_text"],
            "raw_markdown": raw_snapshot["raw_markdown"],
            "text": preview_text[:max_chars],
            "markdown": preview_markdown[:max_chars],
            "content": preview_content[:max_chars],
            "output_format": options.output_format,
            "table_count": len(parsed.tables),
            "warning_count": len(parsed.warnings),
            "warnings": parsed.warnings[:5],
            "truncated": len(selected_output) > max_chars,
            "parse_options": options.normalized_dump(),
            "cleanup_report": parsed.cleanup_report,
            "cleanup_score": parsed.cleanup_score,
        }

    async def reparse(
        self,
        file_id: str,
        max_chars: int = DEFAULT_PREVIEW_CHARS,
        options: DocumentParseOptions | None = None,
        progress_callback: ParseProgressCallback | None = None,
    ) -> dict:
        file = self.get_file(file_id)
        options = options or DocumentParseOptions()
        parsed = await self.parse_and_cache(
            file,
            options=options,
            preview=False,
            force_reparse=True,
            progress_callback=progress_callback,
        )
        selected_output = _selected_output(parsed, options)
        preview_text, preview_markdown, preview_content = _preview_payload(parsed, options)
        raw_snapshot = raw_document_snapshot(parsed)
        persisted_markdown = parsed.markdown or parsed.text
        token_count = estimate_tokens(persisted_markdown)
        result_id, sequence_number, kept = self.db.store_library_parse_result(
            file.id,
            provider=parsed.provider,
            parsed_text=selected_output,
            markdown=parsed.markdown or None,
            parse_options=options.normalized_dump(),
            warnings=parsed.warnings,
            token_count=token_count,
        )
        max_chars = max(1, min(max_chars, MAX_PREVIEW_CHARS))
        return {
            "file_id": file.id,
            "filename": file.filename,
            "token_count": token_count,
            "provider": parsed.provider,
            "raw_text": raw_snapshot["raw_text"],
            "raw_markdown": raw_snapshot["raw_markdown"],
            "text": preview_text[:max_chars],
            "markdown": preview_markdown[:max_chars],
            "content": preview_content[:max_chars],
            "output_format": options.output_format,
            "table_count": len(parsed.tables),
            "warning_count": len(parsed.warnings),
            "warnings": parsed.warnings[:5],
            "truncated": len(selected_output) > max_chars,
            "parse_options": options.normalized_dump(),
            "cleanup_report": parsed.cleanup_report,
            "cleanup_score": parsed.cleanup_score,
            "stored_result_id": result_id,
            "stored_sequence_number": sequence_number,
            "kept_results": [item.model_dump(mode="json") for item in kept],
        }

    def _remember_parse_result(
        self,
        file_id: str,
        parsed: ParsedDocument,
        *,
        options: DocumentParseOptions,
        preview: bool,
    ) -> None:
        if preview:
            return
        persisted_markdown = parsed.markdown or parsed.text
        self.db.set_parsed_text(file_id, persisted_markdown, estimate_tokens(persisted_markdown))

    def _parse_cache_paths(
        self,
        file: LibraryFile,
        options: DocumentParseOptions,
        *,
        preview: bool,
    ) -> tuple[Path, Path]:
        cache_key = options.cache_key()
        cache_prefix = file.sha256 if cache_key == "default" else f"{file.sha256}__{cache_key}"
        if preview:
            cache_prefix = f"{file.sha256}__preview" if cache_key == "default" else f"{file.sha256}__preview__{cache_key}"
        return self.cache_root / f"{cache_prefix}.txt", self.cache_root / f"{cache_prefix}.json"

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

    def _delete_bound_exam_papers_by_sha(self, sha256: str) -> None:
        with SessionLocal() as session:
            asset_ids = list(session.scalars(select(Asset.id).where(Asset.sha256 == sha256)))
            if not asset_ids:
                return
            paper_ids = list(session.scalars(select(ExamPaper.id).where(ExamPaper.asset_id.in_(asset_ids))))
            if not paper_ids:
                return
            service = PaperService(session)
            for paper_id in paper_ids:
                service.delete_paper(paper_id)


def _preview_payload(parsed: ParsedDocument, options: DocumentParseOptions) -> tuple[str, str, str]:
    preview_markdown = parsed.markdown or parsed.text
    preview_text = parsed.text or preview_markdown
    if not preview_markdown.strip():
        placeholder = (
            "[No text extracted. This file may be a low-quality scan, an image-only page, "
            "or PP-StructureV3 may not be installed correctly.]"
        )
        preview_markdown = placeholder
        preview_text = placeholder
    preview_content = options.select_output(text=preview_text, markdown=preview_markdown)
    return preview_text, preview_markdown, preview_content


def _selected_output(parsed: ParsedDocument, options: DocumentParseOptions) -> str:
    return options.select_output(text=parsed.text, markdown=parsed.markdown)


def _is_stale_parse_cache(parsed: ParsedDocument) -> bool:
    provider = parsed.provider.lower()
    if provider.startswith("pdf_ocr_pipeline/rapid") or provider == "rapidocr_onnxruntime":
        return True
    payload = "\n".join(
        str(part or "")
        for part in (parsed.raw_markdown, parsed.markdown, parsed.raw_text, parsed.text)
        if str(part or "").strip()
    )
    if ('src="imgs/' in payload or "src='imgs/" in payload) and not (parsed.markdown_image_roots or []):
        return True
    return False
