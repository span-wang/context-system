from __future__ import annotations

import base64
import hashlib
import json
import logging
import mimetypes
import re
import shutil
from datetime import datetime, timezone
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Asset, ExamPaper, PaperSection, Subject
from app.repositories.papers import PaperRepository
from app.schemas.papers import (
    PaperDeleteResponse,
    PaperDetailResponse,
    PaperParseExecutionMode,
    PaperParseResponse,
    PaperSectionResponse,
    PaperSummary,
    PaperUploadResponse,
)
from app.services.paper_dataset import (
    export_paper_parser_sample,
    resolve_paper_dataset_root,
    resolve_paper_dataset_sample_dir,
    should_auto_export_paper_dataset,
)
from app.services.paper_ai_cleanup import clean_and_structure_paper_source
from app.services.paper_review_ai import normalize_analysis
from app.services.paper_review_standardize_jobs import (
    cancel_active_paper_review_ai_standardize_jobs,
    start_paper_review_ai_standardize_jobs,
)
from library.parse_options import DocumentParseOptions
from library.pdf_ocr_pipeline import (
    CHECKPOINT_NAMESPACE_FILENAME,
    OCRPipelineOptions,
    _get_paddle_ocr_settings,
    _get_pdf_ocr_checkpoint_root,
)
from library.parser import (
    ParsedDocument,
    _get_paddleocr_vl15_runtime_settings,
    deserialize_parsed_document,
    parse_document,
)

PaperParseProgressCallback = Callable[[str, int, dict[str, object] | None], None]

logger = logging.getLogger(__name__)

ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".docx", ".md", ".txt"}
ALLOWED_UPLOAD_MIME_PREFIXES = ("application/", "image/", "text/")

@dataclass(slots=True)
class ParsedSection:
    title: str
    section_type: str
    sort_order: int


@dataclass(slots=True)
class ParsedQuestionPayload:
    question_no: str
    node_role: str
    question_type: str
    group_stem: str | None
    material_text: str | None
    stem_text: str
    options_json: list[str]
    answer_text: str | None
    analysis_text: str | None
    difficulty_level: int
    quality_score: float
    subquestion_count: int
    quality_issues: list[str]
    source_raw_text: str
    subquestions: list["ParsedQuestionPayload"] = field(default_factory=list)


@dataclass(slots=True)
class PaperCleanupSummary:
    removed_asset: bool = False
    removed_storage_file: bool = False
    removed_dataset_dir: bool = False
    removed_parsed_cache_files: int = 0
    removed_pdf_checkpoint_dirs: int = 0
    warnings: list[str] | None = None


@dataclass(slots=True)
class PaperPreviewResponse:
    paper_id: int
    asset_id: int
    filename: str
    provider: str
    raw_text: str
    raw_markdown: str
    text: str
    markdown: str
    content: str
    token_count: int
    cleanup_report: dict[str, Any]
    cleanup_score: float | None
    parse_options: dict[str, object]
    parse_runtime: dict[str, object]
    execution_mode: str
    cached_at: str | None
    warnings: list[str]


@dataclass(slots=True)
class PaperPreviewCacheSnapshot:
    parsed_document: ParsedDocument
    options: DocumentParseOptions
    parse_options: dict[str, object]
    execution_mode: str
    token_count: int
    saved_at: str | None


class PaperService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = PaperRepository(session)

    def list_papers(self) -> list[PaperSummary]:
        summaries: list[PaperSummary] = []
        for paper in self.repository.list_papers():
            asset = self.repository.get_asset(paper.asset_id)
            category = self.repository.get_subject_category(paper.category_id)
            summaries.append(
                PaperSummary.model_validate(
                    {
                        **paper.__dict__,
                        "category": category.name if category else _category_from_asset_tags(asset.tags_json if asset else None),
                    }
                )
            )
        return summaries

    def get_paper(self, paper_id: int) -> PaperDetailResponse:
        paper = self.repository.get_paper(paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="试卷不存在")
        subject = self.repository.get_subject(paper.subject_id)
        category = self.repository.get_subject_category(paper.category_id)
        asset = self.repository.get_asset(paper.asset_id)
        active_job = self.repository.find_active_parse_job(paper.id)
        sections = [PaperSectionResponse.model_validate(item) for item in self.repository.list_sections(paper.id)]
        return PaperDetailResponse.model_validate(
            {
                **paper.__dict__,
                "subject_name": subject.name if subject else None,
                "category": category.name if category else _category_from_asset_tags(asset.tags_json if asset else None),
                "asset_filename": asset.filename if asset else None,
                "asset_parse_status": asset.parse_status if asset else None,
                "active_parse_job_id": active_job.id if active_job else None,
                "active_parse_job_status": active_job.status if active_job else None,
                "active_parse_stage": (active_job.scope_config_json or {}).get("stage") if active_job else None,
                "active_parse_progress": active_job.progress if active_job else None,
                "sections": sections,
            }
        )

    def delete_paper(self, paper_id: int) -> PaperDeleteResponse:
        paper = self.repository.get_paper(paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="试卷不存在")
        asset = self.repository.get_asset(paper.asset_id)
        asset_cleanup_snapshot = (
            {
                "id": asset.id,
                "storage_path": asset.storage_path,
                "sha256": asset.sha256,
                "filename": asset.filename,
                "mime_type": asset.mime_type,
            }
            if asset is not None
            else None
        )
        paper_name = paper.paper_name
        parse_jobs = self.repository.list_jobs(paper.id)
        should_delete_asset = bool(
            asset is not None
            and self.repository.count_papers_by_asset(asset.id, exclude_paper_id=paper.id) == 0
        )
        should_cleanup_sha_cache = bool(
            asset is not None
            and self.repository.count_assets_by_sha(asset.sha256, exclude_asset_id=asset.id) == 0
        )
        cleanup_parse_options = [
            job_options
            for job in parse_jobs
            if isinstance((job.scope_config_json or {}).get("parse_options"), dict)
            and (job_options := (job.scope_config_json or {}).get("parse_options"))
        ]
        cleanup_summary = PaperCleanupSummary(removed_asset=should_delete_asset, warnings=[])
        finished_at = datetime.utcnow()
        for job in parse_jobs:
            if job.status in {"completed", "failed"}:
                continue
            scope = dict(job.scope_config_json or {})
            scope["stage"] = "failed"
            detail = dict(scope.get("detail") or {})
            detail.update({"paper_id": paper.id, "termination_reason": "paper_deleted"})
            scope["detail"] = detail
            job.scope_config_json = scope
            job.status = "failed"
            job.progress = 100
            job.error_message = "试卷已删除，解析任务已终止"
            job.finished_at = finished_at
        self.repository.delete_paper(paper.id)
        self.session.commit()
        if should_delete_asset and asset_cleanup_snapshot is not None:
            try:
                cleanup_summary = self._cleanup_deleted_asset_files(
                    asset_cleanup_snapshot,
                    cleanup_parse_options,
                    cleanup_sha_cache=should_cleanup_sha_cache,
                )
                cleanup_summary.removed_asset = True
            except Exception as exc:
                cleanup_summary.warnings.append(f"素材清理失败：{exc}")
        try:
            if self._cleanup_deleted_paper_dataset(paper_id, paper_name):
                cleanup_summary.removed_dataset_dir = True
        except Exception as exc:
            cleanup_summary.warnings.append(f"训练样本清理失败：{exc}")
        logger.info(
            "paper_delete_cleanup paper_id=%s asset_id=%s removed_asset=%s removed_storage_file=%s removed_dataset_dir=%s removed_parsed_cache_files=%s removed_pdf_checkpoint_dirs=%s warnings=%s",
            paper_id,
            asset_cleanup_snapshot["id"] if asset_cleanup_snapshot is not None else None,
            cleanup_summary.removed_asset,
            cleanup_summary.removed_storage_file,
            cleanup_summary.removed_dataset_dir,
            cleanup_summary.removed_parsed_cache_files,
            cleanup_summary.removed_pdf_checkpoint_dirs,
            cleanup_summary.warnings or [],
        )
        return PaperDeleteResponse(
            id=paper_id,
            paper_name=paper_name,
            deleted=True,
            removed_asset=cleanup_summary.removed_asset,
            removed_storage_file=cleanup_summary.removed_storage_file,
            removed_dataset_dir=cleanup_summary.removed_dataset_dir,
            removed_parsed_cache_files=cleanup_summary.removed_parsed_cache_files,
            removed_pdf_checkpoint_dirs=cleanup_summary.removed_pdf_checkpoint_dirs,
            cleanup_warnings=cleanup_summary.warnings or [],
        )

    def parse_paper(
        self,
        paper_id: int,
        options: DocumentParseOptions | None = None,
        execution_mode: PaperParseExecutionMode = "full_chain",
        progress_callback: PaperParseProgressCallback | None = None,
    ) -> PaperParseResponse:
        options = options or DocumentParseOptions()
        _emit_parse_progress(progress_callback, "prepare", 5, {"paper_id": paper_id, "execution_mode": execution_mode})
        paper = self.repository.get_paper(paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="试卷不存在")
        asset = self.repository.get_asset(paper.asset_id)
        if asset is None:
            raise HTTPException(status_code=422, detail="试卷未绑定素材")

        settings = get_settings()
        cached_snapshot: PaperPreviewCacheSnapshot | None = None
        effective_options = options
        if execution_mode == "ai_cleanup_split":
            cached_snapshot = _read_paper_parse_preview_snapshot(paper=paper, asset=asset)

        self._sync_parse_runtime_status(paper, asset, "prepare")
        if cached_snapshot is not None:
            parsed_document = cached_snapshot.parsed_document
            effective_options = cached_snapshot.options
        else:
            storage_path = Path(asset.storage_path)
            if not storage_path.is_absolute():
                storage_path = settings.storage.root_path / storage_path
            if not storage_path.exists():
                raise HTTPException(status_code=404, detail=f"素材文件不存在：{asset.storage_path}")

            _emit_parse_progress(
                progress_callback,
                "read_file",
                10,
                {"filename": asset.filename, "execution_mode": execution_mode},
            )
            self._sync_parse_runtime_status(paper, asset, "read_file")
            data = storage_path.read_bytes()
            parsed_document = parse_document(
                data,
                asset.filename,
                asset.mime_type,
                options=effective_options,
                progress_callback=progress_callback,
                cache_namespace=f"paper_asset_{asset.id}",
            )
            _write_paper_parse_preview_cache(
                paper=paper,
                asset=asset,
                parsed_document=parsed_document,
                options=effective_options,
                execution_mode=execution_mode,
                parse_runtime=_build_parse_runtime_snapshot(
                    effective_options,
                    provider=parsed_document.provider,
                    execution_mode=execution_mode,
                ),
            )

        parsed_output = effective_options.select_output(text=parsed_document.text, markdown=parsed_document.markdown).strip()
        source_text, raw_source_text = _select_ai_cleanup_source(parsed_document, effective_options)
        source_text = source_text or parsed_output
        raw_source_text = raw_source_text or source_text
        if not source_text:
            fallback_cached_text = (asset.parsed_text or "").strip()
            if fallback_cached_text:
                source_text = fallback_cached_text
                raw_source_text = fallback_cached_text
                parsed_document = ParsedDocument(
                    text=fallback_cached_text,
                    markdown=fallback_cached_text,
                    provider="asset_parsed_text_fallback",
                    used_ocr=True,
                    warnings=[*parsed_document.warnings, "PDF 重新解析为空，已回退到 assets.parsed_text"],
                    raw_text=fallback_cached_text,
                    raw_markdown=fallback_cached_text,
                )
            else:
                asset.parse_status = "empty"
                asset.ocr_status = "empty"
                paper.status = "parse_failed"
                self.session.commit()
                raise HTTPException(status_code=422, detail="未能从试卷中解析出文本")

        parse_runtime = _build_parse_runtime_snapshot(
            effective_options,
            provider=parsed_document.provider,
            execution_mode=execution_mode,
        )
        if cached_snapshot is not None:
            parse_runtime["source_reused_from_cache"] = True
            parse_runtime["source_execution_mode"] = cached_snapshot.execution_mode

        if execution_mode == "ocr_only":
            token_count = max(1, len(source_text) // 2)
            if paper.status != "parsed":
                paper.status = "source_ready"
            if asset.parse_status != "parsed":
                asset.parse_status = "source_ready"
                asset.parsed_text = source_text
            asset.ocr_status = "completed"
            asset.token_count = token_count
            self.session.commit()
            _emit_parse_progress(
                progress_callback,
                "completed",
                100,
                {"execution_mode": execution_mode, "token_count": token_count},
            )
            return PaperParseResponse(
                paper_id=paper.id,
                asset_id=asset.id,
                parse_status=asset.parse_status,
                paper_status=paper.status,
                question_count=paper.total_question_count,
                section_count=len(self.repository.list_sections(paper.id)),
                tagged_count=0,
                preview=source_text[:300],
                provider=parsed_document.provider,
                output_format=effective_options.output_format,
                warnings=list(parsed_document.warnings or [])[:10],
                parse_options=effective_options.normalized_dump(),
                parse_runtime=parse_runtime,
                execution_mode=execution_mode,
                token_count=token_count,
            )

        cancel_active_paper_review_ai_standardize_jobs(
            self.session,
            paper_id=paper.id,
            reason="试卷已重新切题，旧解题任务已作废",
        )
        tenant = self.repository.get_default_tenant(settings.app.default_tenant_code)
        if tenant is None:
            raise HTTPException(status_code=500, detail="默认租户尚未初始化")
        operator = self.repository.get_default_user(tenant.id)
        operator_id = operator.id if operator else None
        subject_id = paper.subject_id
        if subject_id is None:
            subject_id = asset.subject_id
        if subject_id is None:
            first_subject = self.repository.list_knowledge_points(None)
            if first_subject:
                subject_id = first_subject[0].subject_id
        if subject_id is None:
            raise HTTPException(status_code=422, detail="试卷或素材必须绑定学科后才能切题")
        subject = self.repository.get_subject(subject_id)
        category = self.repository.get_subject_category(paper.category_id)

        _emit_parse_progress(
            progress_callback,
            "ai_cleanup",
            72,
            {
                "text_length": len(source_text),
                "execution_mode": execution_mode,
            },
        )
        self._sync_parse_runtime_status(paper, asset, "ai_cleanup")
        ai_cleanup = clean_and_structure_paper_source(
            source_text,
            raw_source_text=raw_source_text,
            paper_name=paper.paper_name,
            subject_name=subject.name if subject else None,
            category_name=category.name if category else _category_from_asset_tags(asset.tags_json if asset else None),
        )
        if not (ai_cleanup.ai_sections or []):
            fallback_ai_cleanup = clean_and_structure_paper_source(
                source_text,
                raw_source_text=raw_source_text,
                paper_name=paper.paper_name,
            )
            if fallback_ai_cleanup.ai_sections:
                merged_warnings = [*ai_cleanup.warnings, "AI 切题首次未产出有效 sections，已使用精简提示重试成功", *fallback_ai_cleanup.warnings]
                ai_cleanup = fallback_ai_cleanup
                ai_cleanup.warnings = merged_warnings[:20]
        ai_source_text = ai_cleanup.ai_source_text.strip() or source_text
        split_source_text = ai_source_text
        ai_prediction = ai_cleanup.ai_prediction if isinstance(ai_cleanup.ai_prediction, dict) else {}

        _emit_parse_progress(
            progress_callback,
            "split_questions",
            76,
            {
                "text_length": len(split_source_text),
                "execution_mode": execution_mode,
            },
        )
        self._sync_parse_runtime_status(paper, asset, "split_questions")
        parsed_sections, section_questions = _build_parsed_sections_from_ai_prediction(ai_prediction)
        if not parsed_sections:
            raise HTTPException(status_code=422, detail=_build_ai_split_failure_detail(ai_cleanup))
        split_strategy = "ai_prediction"
        _emit_parse_progress(
            progress_callback,
            "build_sections",
            80,
            {
                "section_count": len(parsed_sections),
                "split_strategy": split_strategy,
                "execution_mode": execution_mode,
            },
        )
        self.repository.delete_parse_outputs(paper.id)
        created_sections: list[PaperSection] = []

        for section_index, parsed_section in enumerate(parsed_sections, start=1):
            section = self.repository.create_section(
                PaperSection(
                    tenant_id=paper.tenant_id,
                    paper_id=paper.id,
                    section_name=parsed_section.title,
                    question_type=parsed_section.section_type,
                    start_no=None,
                    end_no=None,
                    score=None,
                    sort_order=parsed_section.sort_order,
                    created_by=operator_id,
                    updated_by=operator_id,
                )
            )
            created_sections.append(section)
            self._sync_parse_runtime_status(paper, asset, "build_sections")
            questions_in_section = section_questions[section_index - 1] if section_index - 1 < len(section_questions) else []
            section_question_count = sum(_count_parsed_leaf_questions(question) for question in questions_in_section)
            if section_question_count:
                start_no = 1 if not created_sections[:-1] else (created_sections[-2].end_no or 0) + 1
                section.start_no = start_no
                section.end_no = start_no + section_question_count - 1
            section.question_type = parsed_section.section_type

        tagged_count = 0

        asset.parsed_text = split_source_text
        asset.token_count = max(1, len(split_source_text) // 2)
        asset.parse_status = "parsed"
        asset.ocr_status = "completed"
        paper.status = "parsed"
        review_sync_count = sum(
            _count_parsed_leaf_questions(question)
            for questions in section_questions
            for question in questions
        )
        review_payloads = [
            {
                "section_id": created_section.id,
                "title": parsed_section.title,
                "section_type": parsed_section.section_type,
                "sort_order": parsed_section.sort_order,
                "questions": [
                    _parsed_question_payload_to_dict(question)
                    for question in (section_questions[index] if index < len(section_questions) else [])
                ],
            }
            for index, (created_section, parsed_section) in enumerate(zip(created_sections, parsed_sections))
        ]
        try:
            from app.services.paper_review import PaperReviewService

            review_sync = PaperReviewService(self.session).sync_questions_from_sections(
                paper_id=paper.id,
                section_payloads=review_payloads,
                operator_id=operator_id,
                commit=False,
            )
            review_sync_count = review_sync.imported_count
            paper.review_status = "pending"
        except Exception as exc:
            logger.warning("Skip paper review sync during parse because paper_review module is unavailable: %s", exc)
        paper.total_question_count = review_sync_count
        self.session.commit()
        ai_standardize_jobs = []
        ai_standardize_job_warning: str | None = None
        if execution_mode == "full_chain":
            try:
                ai_standardize_jobs = start_paper_review_ai_standardize_jobs(
                    self.session,
                    paper_id=paper.id,
                    only_missing_solutions=True,
                )
            except Exception as exc:
                ai_standardize_job_warning = f"解题任务提交失败：{str(exc)[:120]}"
                logger.warning("Skip paper review ai standardize job submission during parse: %s", exc)
        ai_standardize_job_ids = [job.id for job in ai_standardize_jobs]
        ai_standardize_requested_count = sum(
            int(((job.scope_config_json or {}).get("requested_count") or 0))
            for job in ai_standardize_jobs
        )
        dataset_sample_path: str | None = None
        dataset_export_error: str | None = None
        dataset_warnings: list[str] = []
        if should_auto_export_paper_dataset():
            try:
                sample_dir = export_paper_parser_sample(
                    paper_id=paper.id,
                    paper_name=paper.paper_name,
                    source_text=source_text,
                    ai_source_text=ai_source_text,
                    ai_prediction=ai_prediction,
                    ai_cleanup_debug=ai_cleanup.debug_payload,
                    raw_source_text=raw_source_text,
                    paper_status=paper.status,
                    paper_review_status=paper.review_status,
                    exam_year=paper.exam_year,
                    exam_month=paper.exam_month,
                    exam_region=paper.exam_region,
                    paper_type=paper.paper_type,
                    subject_name=subject.name if subject else None,
                    subject_code=subject.code if subject else None,
                    category_name=category.name if category else _category_from_asset_tags(asset.tags_json if asset else None),
                    asset_id=asset.id,
                    asset_filename=asset.filename,
                    asset_mime_type=asset.mime_type,
                    asset_storage_path=asset.storage_path,
                    asset_parse_status=asset.parse_status,
                    asset_ocr_status=asset.ocr_status,
                    provider=parsed_document.provider,
                    markdown_image_roots=parsed_document.markdown_image_roots,
                    parse_options={
                        **effective_options.normalized_dump(),
                        "split_source_file": "ai_source.txt",
                        "ai_cleanup": ai_cleanup.cleanup_report,
                        "split_strategy": split_strategy,
                        "execution_mode": execution_mode,
                    },
                    stored_section_count=len([section for section in created_sections if section.start_no is not None]),
                    stored_question_count=review_sync_count,
                    stored_needs_review_count=0,
                )
                dataset_sample_path = str(sample_dir)
            except Exception as exc:
                dataset_export_error = str(exc)
                dataset_warnings.append(f"样本自动导入失败：{dataset_export_error}")
        _emit_parse_progress(
            progress_callback,
            "completed",
            100,
            {
                "question_count": paper.total_question_count,
                "split_strategy": split_strategy,
                "token_count": asset.token_count,
                "execution_mode": execution_mode,
            },
        )
        return PaperParseResponse(
            paper_id=paper.id,
            asset_id=asset.id,
            parse_status=asset.parse_status,
            paper_status=paper.status,
            question_count=paper.total_question_count,
            section_count=len([section for section in created_sections if section.start_no is not None]),
            tagged_count=tagged_count,
            preview=split_source_text[:300],
            provider=parsed_document.provider,
            output_format=effective_options.output_format,
            warnings=[*dataset_warnings, *([ai_standardize_job_warning] if ai_standardize_job_warning else []), *ai_cleanup.warnings, *parsed_document.warnings][:10],
            parse_options={
                **effective_options.normalized_dump(),
                "split_source_file": "ai_source.txt",
                "ai_cleanup": ai_cleanup.cleanup_report,
                "split_strategy": split_strategy,
            },
            parse_runtime=parse_runtime,
            execution_mode=execution_mode,
            token_count=asset.token_count,
            dataset_sample_path=dataset_sample_path,
            dataset_auto_exported=bool(dataset_sample_path),
            dataset_export_error=dataset_export_error,
            ai_standardize_job_count=len(ai_standardize_jobs),
            ai_standardize_requested_count=ai_standardize_requested_count,
            ai_standardize_job_ids=ai_standardize_job_ids,
        )

    def preview_paper(
        self,
        paper_id: int,
        options: DocumentParseOptions | None = None,
        progress_callback: PaperParseProgressCallback | None = None,
    ) -> PaperPreviewResponse:
        paper = self.repository.get_paper(paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="试卷不存在")
        asset = self.repository.get_asset(paper.asset_id)
        if asset is None:
            raise HTTPException(status_code=422, detail="试卷未绑定素材")
        _emit_parse_progress(progress_callback, "cache", 70, {"paper_id": paper_id, "cache_only": True})
        cached_preview = _read_paper_parse_preview_cache(paper=paper, asset=asset)
        if cached_preview is None:
            raise HTTPException(status_code=409, detail="暂无正式解析缓存，请先执行正式解析")
        return cached_preview

    async def upload_paper(
        self,
        file: UploadFile,
        paper_name: str,
        subject_id: int | None = None,
        subject_code: str | None = None,
        subject_name: str | None = None,
        category: str | None = None,
        exam_year: int | None = None,
        exam_month: int | None = None,
        exam_region: str | None = None,
        exam_type: str | None = None,
        paper_type: str | None = None,
        paper_code: str | None = None,
    ) -> PaperUploadResponse:
        filename = (file.filename or "upload.bin").strip() or "upload.bin"
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
            raise HTTPException(status_code=422, detail=f"暂不支持的试卷文件类型：{suffix or 'unknown'}")

        mime_type = file.content_type or "application/octet-stream"
        if not mime_type.startswith(ALLOWED_UPLOAD_MIME_PREFIXES):
            raise HTTPException(status_code=422, detail=f"暂不支持的 MIME 类型：{mime_type}")

        data = await file.read()
        if not data:
            raise HTTPException(status_code=422, detail="上传文件为空")

        name = paper_name.strip() or Path(filename).stem
        settings = get_settings()
        tenant = self.repository.get_default_tenant(settings.app.default_tenant_code)
        if tenant is None:
            raise HTTPException(status_code=500, detail="默认租户尚未初始化")

        operator = self.repository.get_default_user(tenant.id)
        operator_id = operator.id if operator else None
        subject = self._resolve_upload_subject(
            tenant.id,
            operator_id,
            subject_id=subject_id,
            subject_code=subject_code,
            subject_name=subject_name,
        )
        normalized_category = category.strip() if category else None
        subject_category = (
            self.repository.ensure_subject_category(tenant.id, subject.id, normalized_category, operator_id)
            if normalized_category and subject
            else None
        )
        if subject_id is not None and subject is None:
            raise HTTPException(status_code=422, detail="学科不存在")

        sha256 = hashlib.sha256(data).hexdigest()
        yyyymm = datetime.utcnow().strftime("%Y%m")
        storage_key = f"papers/{yyyymm}/{sha256}-{uuid4().hex}{suffix}"
        storage_path = settings.storage.root_path / storage_key
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_bytes(data)

        asset = self.repository.create_asset(
            Asset(
                tenant_id=tenant.id,
                subject_id=subject.id if subject else None,
                asset_type=suffix.lstrip(".") or "file",
                source_type="exam",
                source_title=name,
                filename=filename,
                mime_type=mime_type,
                storage_path=storage_key,
                sha256=sha256,
                file_size=len(data),
                parse_status="pending",
                ocr_status="pending",
                year=exam_year,
                region=exam_region.strip() if exam_region else None,
                tags_json=_paper_tags(normalized_category),
                created_by=operator_id,
                updated_by=operator_id,
            )
        )

        paper = self.repository.create_paper(
            ExamPaper(
                tenant_id=tenant.id,
                subject_id=(subject.id if subject else None) or asset.subject_id,
                category_id=subject_category.id if subject_category else None,
                asset_id=asset.id,
                paper_name=name,
                paper_code=paper_code.strip() if paper_code else None,
                exam_year=exam_year,
                exam_month=exam_month,
                exam_region=exam_region.strip() if exam_region else None,
                exam_type=exam_type.strip() if exam_type else None,
                paper_type=paper_type.strip() if paper_type else "真题",
                source_channel="平台上传",
                status="uploaded",
                total_question_count=0,
                total_score=None,
                parsed_version=1,
                review_status="pending",
                created_by=operator_id,
                updated_by=operator_id,
            )
        )
        self.session.commit()
        return self._upload_response(paper, asset)

    def _resolve_upload_subject(
        self,
        tenant_id: int,
        operator_id: int | None,
        *,
        subject_id: int | None = None,
        subject_code: str | None = None,
        subject_name: str | None = None,
    ) -> Subject | None:
        if subject_id is not None:
            return self.repository.get_subject_by_id(subject_id)
        code = subject_code.strip() if subject_code else ""
        name = subject_name.strip() if subject_name else ""
        if not code and not name:
            return None
        subject = self.repository.get_subject_by_code_or_name(code, name)
        if subject:
            return subject
        return self.repository.create_subject(
            Subject(
                tenant_id=tenant_id,
                code=code or _subject_code_from_name(name),
                name=name or code,
                status="active",
                created_by=operator_id,
                updated_by=operator_id,
            )
        )

    def _upload_response(self, paper: ExamPaper, asset: Asset) -> PaperUploadResponse:
        return PaperUploadResponse.model_validate(
            {
                "id": paper.id,
                "asset_id": asset.id,
                "paper_name": paper.paper_name,
                "filename": asset.filename,
                "sha256": asset.sha256,
                "status": paper.status,
                "review_status": paper.review_status,
                "asset_parse_status": asset.parse_status,
            }
        )

    def _cleanup_deleted_asset_files(
        self,
        asset: dict[str, str | int],
        parse_option_dumps: list[dict[str, Any]],
        *,
        cleanup_sha_cache: bool,
    ) -> PaperCleanupSummary:
        summary = PaperCleanupSummary(warnings=[])
        storage_path = _resolve_asset_storage_path(asset["storage_path"])
        if storage_path.exists():
            storage_path.unlink(missing_ok=True)
            summary.removed_storage_file = True
        summary.removed_parsed_cache_files = self._cleanup_parsed_text_cache(
            int(asset["id"]),
            asset["sha256"],
            cleanup_sha_cache=cleanup_sha_cache,
        )
        summary.removed_pdf_checkpoint_dirs = self._cleanup_pdf_parse_cache(
            asset_id=int(asset["id"]),
            asset=asset,
            parse_option_dumps=parse_option_dumps,
            cleanup_sha_cache=cleanup_sha_cache,
        )
        return summary

    def _cleanup_parsed_text_cache(self, asset_id: int, sha256: str, *, cleanup_sha_cache: bool) -> int:
        cache_root = get_settings().storage.root_path / "cache" / "parsed"
        if not cache_root.exists():
            return 0
        patterns = [f"paper_asset_{asset_id}__*.txt", f"paper_asset_{asset_id}__*.json"]
        if cleanup_sha_cache:
            patterns.extend(
                (
                    f"{sha256}.txt",
                    f"{sha256}.json",
                    f"{sha256}__*.txt",
                    f"{sha256}__*.json",
                )
            )
        removed_count = 0
        for pattern in patterns:
            for cache_path in cache_root.glob(pattern):
                if cache_path.is_file():
                    cache_path.unlink(missing_ok=True)
                    removed_count += 1
        return removed_count

    def _cleanup_pdf_parse_cache(
        self,
        *,
        asset_id: int,
        asset: dict[str, str | int],
        parse_option_dumps: list[dict[str, Any]],
        cleanup_sha_cache: bool,
    ) -> int:
        if Path(asset.get("filename") or "").suffix.lower() != ".pdf" and asset.get("mime_type") != "application/pdf":
            return 0
        checkpoint_root = _get_pdf_ocr_checkpoint_root(ensure_exists=False)
        removed_count = 0
        if cleanup_sha_cache and checkpoint_root.exists():
            for root in (checkpoint_root, checkpoint_root / "layout"):
                removed_count += self._cleanup_sha_cache_directories(root, asset["sha256"])
        removed_count += self._cleanup_namespace_cache_directories(checkpoint_root, f"paper_asset_{asset_id}")
        for cache_dir in _build_pdf_checkpoint_dirs(asset_id, asset["sha256"], parse_option_dumps):
            if cache_dir.exists():
                shutil.rmtree(cache_dir, ignore_errors=True)
                removed_count += 1
        self._prune_empty_dirs(checkpoint_root)
        return removed_count

    def _cleanup_sha_cache_directories(self, root: Path, sha256: str) -> int:
        if not root.exists():
            return 0
        removed_count = 0
        for fingerprint_path in root.rglob("source.sha256"):
            cache_dir = fingerprint_path.parent
            if not cache_dir.is_dir():
                continue
            try:
                cached_sha256 = fingerprint_path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if cached_sha256 == sha256:
                shutil.rmtree(cache_dir, ignore_errors=True)
                removed_count += 1
        return removed_count

    def _cleanup_namespace_cache_directories(self, root: Path, cache_namespace: str) -> int:
        if not root.exists():
            return 0
        removed_count = 0
        seen_dirs: set[Path] = set()
        for marker_path in root.rglob(CHECKPOINT_NAMESPACE_FILENAME):
            cache_dir = marker_path.parent
            if cache_dir in seen_dirs or not cache_dir.is_dir():
                continue
            try:
                recorded_namespace = marker_path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if recorded_namespace != cache_namespace:
                continue
            shutil.rmtree(cache_dir, ignore_errors=True)
            seen_dirs.add(cache_dir)
            removed_count += 1
        return removed_count

    def _prune_empty_dirs(self, root: Path) -> None:
        if not root.exists():
            return
        for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if not path.is_dir():
                continue
            try:
                next(path.iterdir())
            except StopIteration:
                path.rmdir()
            except OSError:
                continue
        try:
            next(root.iterdir())
        except StopIteration:
            root.rmdir()
        except OSError:
            pass

    def _cleanup_deleted_paper_dataset(self, paper_id: int, paper_name: str) -> bool:
        dataset_root = resolve_paper_dataset_root()
        if not dataset_root.exists():
            return False
        sample_dirs = {resolve_paper_dataset_sample_dir(paper_id, paper_name)}
        sample_dirs.update(path for path in dataset_root.glob(f"paper_{paper_id:06d}_*") if path.is_dir())
        removed = False
        for sample_dir in sample_dirs:
            if sample_dir.exists():
                shutil.rmtree(sample_dir, ignore_errors=True)
                removed = True
        return removed

    def _sync_parse_runtime_status(self, paper: ExamPaper, asset: Asset, stage: str) -> None:
        paper.status = _paper_runtime_status(stage)
        asset.parse_status = _asset_runtime_status(stage)
        if stage in {"ocr", "layout_analysis", "ocr_fallback", "vl15"}:
            asset.ocr_status = "running"


def _paper_runtime_status(stage: str) -> str:
    mapping = {
        "prepare": "preparing",
        "read_file": "reading_file",
        "ocr": "ocr_running",
        "layout_analysis": "layout_analyzing",
        "ocr_fallback": "ocr_fallback_running",
        "vl15": "vl15_running",
        "ai_cleanup": "ai_cleaning",
        "split_questions": "splitting_questions",
        "build_sections": "building_sections",
        "tagging": "tagging",
        "saving": "saving",
        "completed": "parsed",
        "failed": "parse_failed",
    }
    return mapping.get(stage, "parsing")


def _asset_runtime_status(stage: str) -> str:
    mapping = {
        "prepare": "preparing",
        "read_file": "reading_file",
        "ocr": "ocr_running",
        "layout_analysis": "layout_analyzing",
        "ocr_fallback": "ocr_fallback_running",
        "vl15": "vl15_running",
        "ai_cleanup": "ai_cleaning",
        "split_questions": "splitting_questions",
        "build_sections": "building_sections",
        "tagging": "tagging",
        "saving": "saving",
        "completed": "parsed",
        "failed": "failed",
    }
    return mapping.get(stage, "parsing")


def _resolve_asset_storage_path(storage_path: str) -> Path:
    candidate = Path(storage_path)
    if candidate.is_absolute():
        return candidate
    return get_settings().storage.root_path / candidate


def _select_ai_cleanup_source(
    parsed_document: ParsedDocument,
    options: DocumentParseOptions,
) -> tuple[str, str]:
    source_text = options.select_output(
        text=parsed_document.raw_text or parsed_document.text,
        markdown=parsed_document.raw_markdown or parsed_document.markdown,
    ).strip()
    if not source_text:
        source_text = options.select_output(
            text=parsed_document.text,
            markdown=parsed_document.markdown,
        ).strip()
    raw_source_text = (parsed_document.raw_text or source_text).strip()
    return source_text, raw_source_text


def _build_pdf_checkpoint_dirs(
    asset_id: int,
    asset_sha256: str,
    parse_option_dumps: list[dict[str, Any]],
) -> set[Path]:
    cache_dirs: set[Path] = set()
    root = _get_pdf_ocr_checkpoint_root()
    parse_candidates: list[dict[str, Any]] = [*parse_option_dumps, {}]
    for dump in parse_candidates:
        raw_preset = str(dump.get("preset") or "").strip()
        try:
            options = DocumentParseOptions(**dump)
        except Exception:
            continue
        pipeline_options = options.to_pipeline_options()
        pipeline_options.cache_namespace = f"paper_asset_{asset_id}"
        cache_dirs.add(
            _build_pdf_ocr_checkpoint_dir(
                root,
                asset_sha256,
                pipeline_options,
                cache_namespace=f"paper_asset_{asset_id}",
            )
        )
        if options.should_use_layout_pipeline():
            cache_dirs.add(
                _build_pdf_layout_checkpoint_dir(
                    root,
                    asset_sha256,
                    pipeline_options,
                    cache_namespace=f"paper_asset_{asset_id}",
                )
            )
        if raw_preset == "auto" and not options.should_use_pdf_ocr("paper.pdf", "application/pdf"):
            fallback_options = OCRPipelineOptions(
                force_ocr=True,
                render_dpi=240,
                cache_namespace=f"paper_asset_{asset_id}",
                trim_margins=True,
                remove_repeated_lines=True,
                watermark_detection=False,
            )
            cache_dirs.add(
                _build_pdf_ocr_checkpoint_dir(
                    root,
                    asset_sha256,
                    fallback_options,
                    cache_namespace=f"paper_asset_{asset_id}",
                )
            )
    return cache_dirs


def _build_pdf_ocr_checkpoint_dir(
    root: Path,
    asset_sha256: str,
    options: OCRPipelineOptions,
    *,
    cache_namespace: str | None = None,
) -> Path:
    options_payload = {
        key: value
        for key, value in asdict(options).items()
        if key not in {"max_pages", "page_chunk_size"}
    }
    payload = json.dumps(
        {
            "sha256": asset_sha256,
            "options": options_payload,
            "cache_namespace": cache_namespace,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return root / digest[:2] / digest


def _build_pdf_layout_checkpoint_dir(
    root: Path,
    asset_sha256: str,
    options: OCRPipelineOptions,
    *,
    cache_namespace: str | None = None,
) -> Path:
    options_payload = {
        key: value
        for key, value in asdict(options).items()
        if key not in {"max_pages", "page_chunk_size"}
    }
    payload = json.dumps(
        {
            "provider": "pp_structure_v3",
            "sha256": asset_sha256,
            "options": options_payload,
            "cache_namespace": cache_namespace,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return root / "layout" / digest[:2] / digest


def _build_parsed_sections_from_ai_prediction(
    prediction: dict[str, Any],
) -> tuple[list[ParsedSection], list[list[ParsedQuestionPayload]]]:
    raw_sections = prediction.get("sections") if isinstance(prediction.get("sections"), list) else []
    sections: list[ParsedSection] = []
    section_questions: list[list[ParsedQuestionPayload]] = []
    for index, item in enumerate(raw_sections, start=1):
        if not isinstance(item, dict):
            continue
        raw_questions = item.get("questions")
        if not isinstance(raw_questions, list):
            continue
        questions: list[ParsedQuestionPayload] = []
        for order, question in enumerate(raw_questions, start=1):
            if not isinstance(question, dict):
                continue
            payload = _to_parsed_question_payload(question)
            if payload is None:
                continue
            questions.append(payload)
        if not questions:
            continue
        sections.append(
            ParsedSection(
                title=str(item.get("title") or "").strip() or f"分区 {index}",
                section_type=str(item.get("section_type") or "mixed").strip() or "mixed",
                sort_order=int(item.get("sort_order") or index),
            )
        )
        section_questions.append(questions)
    return sections, section_questions


def _to_parsed_question_payload(question: dict[str, Any]) -> ParsedQuestionPayload | None:
    stem_text = str(question.get("stem_text") or "").strip()
    source_raw_text = str(question.get("source_raw_text") or "").strip()
    question_no = str(question.get("question_no") or "").strip()
    node_role = str(question.get("node_role") or "").strip() or (
        "group" if isinstance(question.get("subquestions"), list) and (question.get("subquestions") or []) else "standalone"
    )
    question_type = str(question.get("question_type") or "mixed").strip() or "mixed"
    group_stem = str(question.get("group_stem") or question.get("shared_stem") or "").strip() or None
    material_text = str(question.get("material_text") or "").strip() or None
    subquestions = [
        child_payload
        for child_payload in (
            _to_parsed_question_payload(child)
            for child in (question.get("subquestions") or [])
            if isinstance(child, dict)
        )
        if child_payload is not None
    ]
    if node_role == "group":
        stem_text = stem_text or group_stem or material_text or question_no
        if not source_raw_text or not question_no or not stem_text:
            return None
    elif not stem_text or not source_raw_text or not question_no:
        return None
    return ParsedQuestionPayload(
        question_no=question_no,
        node_role=node_role,
        question_type=question_type,
        group_stem=group_stem,
        material_text=material_text,
        stem_text=stem_text,
        options_json=[str(option).strip() for option in (question.get("options") or []) if str(option).strip()],
        answer_text=str(question.get("answer_text") or "").strip() or None,
        analysis_text=normalize_analysis(question.get("analysis_text")),
        difficulty_level=int(question.get("difficulty_level") or 3),
        quality_score=float(question.get("quality_score") or 0.0),
        subquestion_count=int(question.get("subquestion_count") or len(subquestions) or 0),
        quality_issues=[str(issue).strip() for issue in (question.get("quality_issues") or []) if str(issue).strip()],
        source_raw_text=source_raw_text,
        subquestions=subquestions,
    )


def _parsed_question_payload_to_dict(question: ParsedQuestionPayload) -> dict[str, Any]:
    return {
        "question_no": question.question_no,
        "node_role": question.node_role,
        "question_type": question.question_type,
        "group_stem": question.group_stem,
        "material_text": question.material_text,
        "stem_text": question.stem_text,
        "options": question.options_json,
        "answer_text": question.answer_text,
        "analysis_text": question.analysis_text,
        "subquestion_count": question.subquestion_count,
        "quality_score": question.quality_score,
        "quality_issues": question.quality_issues,
        "source_raw_text": question.source_raw_text,
        "subquestions": [_parsed_question_payload_to_dict(child) for child in question.subquestions],
    }


def _count_parsed_leaf_questions(question: ParsedQuestionPayload) -> int:
    if question.node_role != "group" or not question.subquestions:
        return 1
    return sum(_count_parsed_leaf_questions(child) for child in question.subquestions)


def _build_ai_split_failure_detail(ai_cleanup: Any) -> str:
    error = str(getattr(ai_cleanup, "error", "") or "").strip()
    if error:
        return f"AI 切题失败：{error}"
    warnings = getattr(ai_cleanup, "warnings", None)
    if isinstance(warnings, list):
        for item in warnings:
            text = str(item or "").strip()
            if text:
                return f"AI 切题失败：{text}"
    return "AI 切题未生成有效结果"


def _paper_tags(category: str | None) -> list[str]:
    tags = ["真题", "待解析"]
    if category:
        tags.append(f"category:{category}")
    return tags


def _category_from_asset_tags(tags: list[str] | None) -> str | None:
    for tag in tags or []:
        if isinstance(tag, str) and tag.startswith("category:"):
            value = tag.removeprefix("category:").strip()
            return value or None
    return None


def _subject_code_from_name(name: str) -> str:
    base = re.sub(r"[^0-9a-zA-Z]+", "_", name.strip()).strip("_").lower()
    if base:
        return base
    return hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


def _emit_parse_progress(
    callback: PaperParseProgressCallback | None,
    stage: str,
    progress: int,
    detail: dict[str, object] | None = None,
) -> None:
    if callback is None:
        return
    callback(stage, max(0, min(100, progress)), detail)


def _paper_parse_preview_cache_paths(asset_id: int) -> tuple[Path, Path]:
    cache_root = get_settings().storage.root_path / "cache" / "parsed"
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_prefix = f"paper_asset_{asset_id}__latest"
    return cache_root / f"{cache_prefix}.txt", cache_root / f"{cache_prefix}.json"


def _write_paper_parse_preview_cache(
    *,
    paper: ExamPaper,
    asset: Asset,
    parsed_document: ParsedDocument,
    options: DocumentParseOptions,
    execution_mode: str,
    parse_runtime: dict[str, object],
) -> None:
    text_cache_path, structured_cache_path = _paper_parse_preview_cache_paths(asset.id)
    selected_output = options.select_output(
        text=parsed_document.text or "",
        markdown=parsed_document.markdown or parsed_document.text or "",
    ).strip()
    text_cache_path.write_text(selected_output, encoding="utf-8")
    payload = {
        "version": 1,
        "paper_id": paper.id,
        "asset_id": asset.id,
        "filename": asset.filename,
        "mime_type": asset.mime_type,
        "provider": parsed_document.provider,
        "execution_mode": execution_mode,
        "token_count": max(1, len(selected_output) // 2),
        "parse_options": options.normalized_dump(),
        "parse_runtime": parse_runtime,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "document": parsed_document.to_dict(),
    }
    tmp_path = structured_cache_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(structured_cache_path)


def _read_paper_parse_preview_snapshot(*, paper: ExamPaper, asset: Asset) -> PaperPreviewCacheSnapshot | None:
    _, structured_cache_path = _paper_parse_preview_cache_paths(asset.id)
    if not structured_cache_path.exists():
        return None
    try:
        payload = json.loads(structured_cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    document_payload = payload.get("document")
    if not isinstance(document_payload, dict):
        return None
    parsed_document = deserialize_parsed_document(json.dumps(document_payload, ensure_ascii=False))
    if parsed_document is None:
        return None

    parse_options = payload.get("parse_options")
    if not isinstance(parse_options, dict):
        parse_options = {}
    try:
        options = DocumentParseOptions(**parse_options)
    except Exception:
        options = DocumentParseOptions()
    return PaperPreviewCacheSnapshot(
        parsed_document=parsed_document,
        options=options,
        parse_options=parse_options,
        execution_mode=str(payload.get("execution_mode") or "full_chain").strip() or "full_chain",
        token_count=int(payload.get("token_count") or 0),
        saved_at=str(payload.get("saved_at") or "").strip() or None,
    )


def _read_paper_parse_preview_cache(*, paper: ExamPaper, asset: Asset) -> PaperPreviewResponse | None:
    snapshot = _read_paper_parse_preview_snapshot(paper=paper, asset=asset)
    if snapshot is None:
        return None
    _, structured_cache_path = _paper_parse_preview_cache_paths(asset.id)
    try:
        payload = json.loads(structured_cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    parse_runtime = payload.get("parse_runtime")
    if not isinstance(parse_runtime, dict):
        parse_runtime = {}

    parsed_document = snapshot.parsed_document
    options = snapshot.options
    raw_text = parsed_document.raw_text or parsed_document.text or ""
    raw_markdown = parsed_document.raw_markdown or parsed_document.markdown or raw_text
    text = parsed_document.text or ""
    markdown = parsed_document.markdown or text
    selected_markdown = _inline_markdown_images(markdown, getattr(parsed_document, "markdown_image_roots", []) or [])
    content = options.select_output(text=text, markdown=selected_markdown).strip()
    token_count = snapshot.token_count or max(1, len(content or text or markdown) // 2)

    return PaperPreviewResponse(
        paper_id=paper.id,
        asset_id=asset.id,
        filename=str(payload.get("filename") or asset.filename),
        provider=str(payload.get("provider") or parsed_document.provider or "unknown"),
        raw_text=raw_text,
        raw_markdown=raw_markdown,
        text=text,
        markdown=markdown,
        content=content,
        token_count=token_count,
        cleanup_report=dict(parsed_document.cleanup_report or {}),
        cleanup_score=parsed_document.cleanup_score,
        parse_options=snapshot.parse_options,
        parse_runtime=parse_runtime,
        execution_mode=snapshot.execution_mode,
        cached_at=snapshot.saved_at,
        warnings=[str(item) for item in (parsed_document.warnings or []) if str(item).strip()][:10],
    )


def _build_parse_runtime_snapshot(
    options: DocumentParseOptions,
    *,
    provider: str,
    execution_mode: str,
) -> dict[str, object]:
    runtime: dict[str, object] = {
        "provider": provider,
        "execution_mode": execution_mode,
        "options": options.resolved_summary(),
    }
    if options.preset == "vl15" or "vl_1_5" in provider.lower():
        runtime["model_settings"] = _build_vl15_runtime_snapshot()
        return runtime
    ocr_settings = _get_paddle_ocr_settings()
    runtime["model_settings"] = {
        "engine": "paddleocr",
        "ocr_version": str(ocr_settings.get("ocr_version") or ""),
        "text_detection_model_name": str(ocr_settings.get("text_detection_model_name") or ""),
        "text_recognition_model_name": str(ocr_settings.get("text_recognition_model_name") or ""),
        "text_detection_model_dir": ocr_settings.get("text_detection_model_dir"),
        "text_recognition_model_dir": ocr_settings.get("text_recognition_model_dir"),
        "use_textline_orientation": bool(ocr_settings.get("use_textline_orientation")),
        "use_doc_orientation_classify": bool(ocr_settings.get("use_doc_orientation_classify")),
        "use_doc_unwarping": bool(ocr_settings.get("use_doc_unwarping")),
        "device": str(ocr_settings.get("device") or ""),
    }
    return runtime


def _build_vl15_runtime_snapshot() -> dict[str, object]:
    try:
        settings = _get_paddleocr_vl15_runtime_settings()
    except Exception as exc:
        return {
            "engine": "paddleocr_vl_1_5",
            "warning": str(exc),
        }
    return {
        "engine": "paddleocr_vl_1_5",
        "device": str(settings.get("device") or ""),
        "cache_home": str(settings.get("cache_home") or ""),
        "model_source": str(settings.get("model_source") or ""),
        "disable_model_source_check": bool(settings.get("disable_model_source_check")),
    }


def _inline_markdown_images(markdown: str, markdown_image_roots: list[str]) -> str:
    if not markdown or not markdown_image_roots:
        return markdown

    source_roots = [Path(root) for root in markdown_image_roots if str(root).strip()]
    if not source_roots:
        return markdown

    def replace_markdown(match: re.Match[str]) -> str:
        alt_text = match.group(1)
        image_path = match.group(2).replace("\\", "/")
        data_url = _load_markdown_image_data_url(image_path, source_roots)
        if not data_url:
            return match.group(0)
        return f'![{alt_text}]({data_url})'

    def replace_html(match: re.Match[str]) -> str:
        before = match.group(1)
        image_path = match.group(2).replace("\\", "/")
        after = match.group(3)
        data_url = _load_markdown_image_data_url(image_path, source_roots)
        if not data_url:
            return match.group(0)
        return f'<img{before}src="{data_url}"{after}>'

    updated = re.sub(r"!\[([^\]]*)\]\((imgs/[^)\s]+)\)", replace_markdown, markdown)
    updated = re.sub(r'<img([^>]*?)src=["\'](imgs/[^"\']+)["\']([^>]*?)>', replace_html, updated, flags=re.IGNORECASE)
    return updated


def _load_markdown_image_data_url(relative_path: str, source_roots: list[Path]) -> str:
    normalized = relative_path.replace("\\", "/").lstrip("/")
    for source_root in source_roots:
        candidate = source_root / normalized
        if not candidate.exists() and normalized.startswith("imgs/"):
            candidate = source_root / normalized.removeprefix("imgs/")
        if not candidate.exists():
            continue
        raw = candidate.read_bytes()
        mime_type = mimetypes.guess_type(candidate.name)[0] or "image/jpeg"
        encoded = base64.b64encode(raw).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"
    return ""
