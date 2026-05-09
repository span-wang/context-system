from __future__ import annotations

import base64
import hashlib
import json
import logging
import mimetypes
import re
import shutil
from uuid import uuid4
from datetime import datetime
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Asset, ExamPaper, PaperSection, Subject
from app.repositories.papers import PaperRepository
from app.schemas.papers import (
    PaperDeleteResponse,
    PaperDetailResponse,
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
from app.services.paper_parser_rules import parse_sections_with_rules
from app.services.paper_parser_rules.engine import parse_question_block as parse_rule_question_block, parse_sections_from_text
from library.ocr_cleaner import clean_parsed_document
from library.parse_options import DocumentParseOptions
from library.pdf_ocr_pipeline import CHECKPOINT_NAMESPACE_FILENAME, OCRPipelineOptions, _get_pdf_ocr_checkpoint_root
from library.parser import ParsedDocument, parse_document

PaperParseProgressCallback = Callable[[str, int, dict[str, object] | None], None]

logger = logging.getLogger(__name__)

ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".docx", ".md", ".txt"}
ALLOWED_UPLOAD_MIME_PREFIXES = ("application/", "image/", "text/")
QUESTION_SPLIT_PATTERN = re.compile(r"(?m)^\s*(?:#+\s*)?(?:第\s*)?([0-9]{1,3}|[一二三四五六七八九十百]{1,6})\s*[\.、．)]\s*")
OPTION_PATTERN = re.compile(r"(?m)^\s*([A-H])[\.\、．)]\s*(.+?)(?=(?:\n\s*[A-H][\.\、．)]\s*)|\Z)", re.S)
ANSWER_PATTERN = re.compile(
    r"(?ms)^\s*(?:#+\s*)?(?:答案|参考答案|正确答案)\s*[:：]\s*(.+?)(?=^\s*(?:#+\s*)?(?:解析|答案解析|【解析】)\s*(?:[:：]|\n)|\Z)"
)
ANALYSIS_PATTERN = re.compile(r"(?ms)^\s*(?:#+\s*)?(?:解析|答案解析|【解析】)\s*(?:[:：]\s*|\n+)(.+)$")
ANSWER_ANALYSIS_HEADER_PATTERN = re.compile(r"(?m)^\s*(?:#+\s*)?答案与解析\s*$")
INLINE_OPTION_PATTERN = re.compile(r"(?<![A-Za-z0-9\u4e00-\u9fff])([A-H])[\.\、．)]\s*")
OPTION_LINE_PATTERN = re.compile(r"^\s*[A-H][\.\、．)]\s*")
TRAILING_OPTION_HINT_PATTERN = re.compile(r"(?<![A-Za-z0-9])([A-H])\s*$")
ANSWER_HEADER_INLINE_PATTERNS = (
    re.compile(r"(?ms)^\s*(?:#+\s*)?(?:答案|参考答案|正确答案)\s*[:：]\s*"),
    re.compile(r"(?<![\u4e00-\u9fffA-Za-z0-9])(?:答案|参考答案|正确答案)\s*[:：]\s*"),
)
ANALYSIS_HEADER_INLINE_PATTERNS = (
    re.compile(r"(?ms)^\s*(?:#+\s*)?(?:答案解析|【解析】)\s*(?:[:：]\s*|\n+)?"),
    re.compile(r"(?ms)^\s*(?:#+\s*)?解析\s*(?:[:：]\s*|\n+)"),
    re.compile(r"(?<![\u4e00-\u9fffA-Za-z0-9])(?:答案解析|【解析】)\s*(?:[:：]\s*|\n+)?"),
    re.compile(r"(?<![\u4e00-\u9fffA-Za-z0-9])解析\s*[:：]\s*"),
)
SECTION_HEADER_PATTERN = re.compile(
    r"(?m)^\s*(?:#+\s*)?(?:(?:第\s*[一二三四五六七八九十百0-9]+\s*部分)|(?:[一二三四五六七八九十百0-9]+\s*[、.．]))?\s*"
    r"(?P<title>(?:单项选择题|多项选择题|不定项选择题|判断题|填空题|简答题|计算题|案例分析题|综合题|材料分析题))"
    r"[^\n]*$"
)
SUBQUESTION_PATTERN = re.compile(r"(?m)^\s*[(（]([1-9][0-9]{0,2}|[一二三四五六七八九十]+)[)）]\s*")
SUBQUESTION_LABEL_PATTERN = re.compile(r"(?m)(?:^|\s)第\s*([1-9][0-9]{0,2}|[一二三四五六七八九十]+)\s*小题")
MATERIAL_ITEM_PATTERN = re.compile(r"(?m)^\s*(?:[(（][1-9][0-9]{0,2}[)）]|资料[一二三四五六七八九十0-9]+(?:\s*[:：]|$))")
CASE_GROUP_PATTERN = re.compile(r"(?m)^\s*(?:#+\s*)?[（(]([一二三四五六七八九十0-9]+)[)）]\s*$")
SHARED_STEM_CUE_PATTERN = re.compile(
    r"(?:要求\s*[:：]?|根据上述资料|根据下列资料|阅读下列材料|分析回答下列|回答下列|下列小题|不考虑其他因素)"
)
QUESTION_PROMPT_PREFIX_PATTERN = re.compile(r"^(?:根据|下列|关于|对|按照|依据|计算|第\s*[0-9一二三四五六七八九十]+\s*小题)")
EMPTY_ANSWER_SLOT_PATTERN = re.compile(r"[（(]\s*[）)]")
BLANK_PLACEHOLDER_PATTERN = re.compile(r"[（(]?\s*(?:[_＿—–-]\s*){2,}[）)]?|[（(]\s*[）)]")
MULTI_ANSWER_PATTERN = re.compile(r"^[A-H](?:[\s,，/、]+[A-H])+$")
JUDGE_ANSWER_PATTERN = re.compile(r"^(?:正确|错误|对|错|√|×)$")
SECTION_TYPE_MAP = {
    "单项选择题": "single_choice",
    "多项选择题": "multiple_choice",
    "不定项选择题": "multiple_choice",
    "判断题": "judge",
    "填空题": "fill_blank",
    "简答题": "short_answer",
    "计算题": "calculation",
    "案例分析题": "case_analysis",
    "综合题": "composite",
    "材料分析题": "material_analysis",
}


@dataclass(slots=True)
class SplitQuestionBlock:
    raw_text: str
    question_no_override: str | None = None
    stem_prefix: str | None = None


@dataclass(slots=True)
class ParsedSection:
    title: str
    section_type: str
    sort_order: int
    blocks: list[SplitQuestionBlock]


@dataclass(slots=True)
class ParsedQuestionBlock:
    question_no: str
    question_type: str
    stem_text: str
    options_json: list[str]
    answer_text: str | None
    analysis_text: str | None
    difficulty_level: int
    quality_score: float
    subquestion_count: int
    source_section_name: str
    quality_issues: list[str]


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
    warnings: list[str]


@dataclass(slots=True)
class AppendixSolutionEntry:
    question_no: str
    answer_text: str | None = None
    analysis_text: str | None = None


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
        progress_callback: PaperParseProgressCallback | None = None,
    ) -> PaperParseResponse:
        options = options or DocumentParseOptions()
        _emit_parse_progress(progress_callback, "prepare", 5, {"paper_id": paper_id})
        paper = self.repository.get_paper(paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="试卷不存在")
        asset = self.repository.get_asset(paper.asset_id)
        if asset is None:
            raise HTTPException(status_code=422, detail="试卷未绑定素材")

        settings = get_settings()
        storage_path = Path(asset.storage_path)
        if not storage_path.is_absolute():
            storage_path = settings.storage.root_path / storage_path
        if not storage_path.exists():
            raise HTTPException(status_code=404, detail=f"素材文件不存在：{asset.storage_path}")

        self._sync_parse_runtime_status(paper, asset, "prepare")
        _emit_parse_progress(progress_callback, "read_file", 10, {"filename": asset.filename})
        self._sync_parse_runtime_status(paper, asset, "read_file")
        data = storage_path.read_bytes()
        parsed_document = parse_document(
            data,
            asset.filename,
            asset.mime_type,
            options=options,
            progress_callback=progress_callback,
            cache_namespace=f"paper_asset_{asset.id}",
        )
        parsed_document = clean_parsed_document(parsed_document)
        parsed_output = options.select_output(text=parsed_document.text, markdown=parsed_document.markdown).strip()
        split_source_text = (parsed_document.text or parsed_output).strip()
        if not parsed_output:
            asset.parse_status = "empty"
            asset.ocr_status = "empty"
            paper.status = "parse_failed"
            self.session.commit()
            raise HTTPException(status_code=422, detail="未能从试卷中解析出文本")

        tenant = self.repository.get_default_tenant(settings.app.default_tenant_code)
        if tenant is None:
            raise HTTPException(status_code=500, detail="默认租户尚未初始化")
        operator = self.repository.get_default_user(tenant.id)
        operator_id = operator.id if operator else None

        _emit_parse_progress(
            progress_callback,
            "split_questions",
            76,
            {
                "text_length": len(split_source_text),
                "parse_mode": options.parse_mode,
            },
        )
        self._sync_parse_runtime_status(paper, asset, "split_questions")
        parsed_sections = _split_paper_sections(parsed_document, split_source_text)
        _emit_parse_progress(
            progress_callback,
            "build_sections",
            80,
            {"section_count": len(parsed_sections), "parse_mode": options.parse_mode},
        )
        self.repository.delete_parse_outputs(paper.id)
        created_sections: list[PaperSection] = []
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
            section_question_count = len(parsed_section.blocks)
            if section_question_count:
                start_no = 1 if not created_sections[:-1] else (created_sections[-2].end_no or 0) + 1
                section.start_no = start_no
                section.end_no = start_no + section_question_count - 1
            section.question_type = parsed_section.section_type

        tagged_count = 0

        asset.parsed_text = parsed_output
        asset.token_count = max(1, len(parsed_output) // 2)
        asset.parse_status = "parsed"
        asset.ocr_status = "completed"
        paper.status = "parsed"
        review_sync_count = sum(len(section.blocks) for section in parsed_sections)
        review_payloads = [
            {
                "section_id": created_section.id,
                "title": parsed_section.title,
                "section_type": parsed_section.section_type,
                "sort_order": parsed_section.sort_order,
                "blocks": [
                    {
                        "raw_text": block.raw_text,
                        "question_no_override": block.question_no_override,
                        "stem_prefix": block.stem_prefix,
                    }
                    for block in parsed_section.blocks
                ],
            }
            for created_section, parsed_section in zip(created_sections, parsed_sections)
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
        dataset_sample_path: str | None = None
        dataset_export_error: str | None = None
        dataset_warnings: list[str] = []
        if should_auto_export_paper_dataset():
            try:
                sample_dir = export_paper_parser_sample(
                    paper_id=paper.id,
                    paper_name=paper.paper_name,
                    source_text=split_source_text,
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
                    parse_options=options.normalized_dump(),
                    stored_section_count=len([section for section in created_sections if section.start_no is not None]),
                    stored_question_count=review_sync_count,
                    stored_needs_review_count=0,
                )
                dataset_sample_path = str(sample_dir)
            except Exception as exc:
                dataset_export_error = str(exc)
                dataset_warnings.append(f"样本自动导入失败：{dataset_export_error}")
        _emit_parse_progress(progress_callback, "completed", 100, {"question_count": paper.total_question_count})
        return PaperParseResponse(
            paper_id=paper.id,
            asset_id=asset.id,
            parse_status=asset.parse_status,
            paper_status=paper.status,
            question_count=paper.total_question_count,
            section_count=len([section for section in created_sections if section.start_no is not None]),
            tagged_count=tagged_count,
            preview=parsed_output[:300],
            provider=parsed_document.provider,
            parse_mode=options.parse_mode,
            output_format=options.output_format,
            warnings=[*dataset_warnings, *parsed_document.warnings][:10],
            parse_options=options.normalized_dump(),
            dataset_sample_path=dataset_sample_path,
            dataset_auto_exported=bool(dataset_sample_path),
            dataset_export_error=dataset_export_error,
        )

    def preview_paper(
        self,
        paper_id: int,
        options: DocumentParseOptions | None = None,
        progress_callback: PaperParseProgressCallback | None = None,
    ) -> PaperPreviewResponse:
        options = options or DocumentParseOptions()
        paper = self.repository.get_paper(paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="试卷不存在")
        asset = self.repository.get_asset(paper.asset_id)
        if asset is None:
            raise HTTPException(status_code=422, detail="试卷未绑定素材")

        settings = get_settings()
        storage_path = Path(asset.storage_path)
        if not storage_path.is_absolute():
            storage_path = settings.storage.root_path / storage_path
        if not storage_path.exists():
            raise HTTPException(status_code=404, detail=f"素材文件不存在：{asset.storage_path}")

        _emit_parse_progress(progress_callback, "prepare", 5, {"paper_id": paper_id})
        data = storage_path.read_bytes()
        parsed_document = parse_document(
            data,
            asset.filename,
            asset.mime_type,
            options=options,
            progress_callback=progress_callback,
            cache_namespace=f"paper_asset_{asset.id}",
        )
        cleaned_document = clean_parsed_document(parsed_document)
        text = cleaned_document.text or ""
        markdown = cleaned_document.markdown or text
        raw_text = cleaned_document.raw_text or parsed_document.text or text
        raw_markdown = cleaned_document.raw_markdown or parsed_document.markdown or markdown
        raw_markdown = _inline_markdown_images(raw_markdown, getattr(parsed_document, "markdown_image_roots", []) or [])
        markdown = _inline_markdown_images(markdown, getattr(parsed_document, "markdown_image_roots", []) or [])
        preview_text = options.select_output(text=text, markdown=markdown).strip()
        return PaperPreviewResponse(
            paper_id=paper.id,
            asset_id=asset.id,
            filename=asset.filename,
            provider=cleaned_document.provider,
            raw_text=raw_text,
            raw_markdown=raw_markdown,
            text=text,
            markdown=markdown,
            content=preview_text,
            token_count=max(1, len(preview_text) // 2),
            cleanup_report=cleaned_document.cleanup_report,
            cleanup_score=cleaned_document.cleanup_score,
            parse_options=options.normalized_dump(),
            warnings=[*parsed_document.warnings, *cleaned_document.warnings][:10],
        )

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
        if stage in {"ocr", "layout_analysis", "ocr_fallback"}:
            asset.ocr_status = "running"


def _paper_runtime_status(stage: str) -> str:
    mapping = {
        "prepare": "preparing",
        "read_file": "reading_file",
        "ocr": "ocr_running",
        "layout_analysis": "layout_analyzing",
        "ocr_fallback": "ocr_fallback_running",
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


def _build_pdf_checkpoint_dirs(
    asset_id: int,
    asset_sha256: str,
    parse_option_dumps: list[dict[str, Any]],
) -> set[Path]:
    cache_dirs: set[Path] = set()
    root = _get_pdf_ocr_checkpoint_root()
    parse_candidates: list[dict[str, Any]] = [*parse_option_dumps, {}, {"preset": "auto"}]
    for dump in parse_candidates:
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
        if options.preset == "auto" and not options.should_use_pdf_ocr("paper.pdf", "application/pdf"):
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


def _split_paper_sections(document: ParsedDocument | None, text: str) -> list[ParsedSection]:
    if document is not None and document.pages:
        sections = _adapt_rule_sections(parse_sections_with_rules(document))
    else:
        sections = _adapt_rule_sections(parse_sections_from_text(text))
    return _attach_appendix_solutions(sections, text)


def _adapt_rule_sections(rule_sections: list[object]) -> list[ParsedSection]:
    return [
        ParsedSection(
            title=str(getattr(section, "title", "") or "自动切题"),
            section_type=str(getattr(section, "section_type", "mixed") or "mixed"),
            sort_order=int(getattr(section, "sort_order", index)),
            blocks=[
                SplitQuestionBlock(
                    raw_text=str(getattr(block, "raw_text", "") or ""),
                    question_no_override=str(getattr(block, "question_no_override", "") or "").strip() or None,
                    stem_prefix=str(getattr(block, "stem_prefix", "") or "").strip() or None,
                )
                for block in getattr(section, "blocks", [])
                if str(getattr(block, "raw_text", "") or "").strip()
            ],
        )
        for index, section in enumerate(rule_sections, start=1)
        if getattr(section, "blocks", None)
    ]


def _attach_appendix_solutions(sections: list[ParsedSection], text: str) -> list[ParsedSection]:
    appendix_entries = _extract_appendix_solution_entries(text)
    if not appendix_entries:
        return sections

    for section in sections:
        for block in section.blocks:
            base_text = _strip_appendix_from_block(block.raw_text)
            parsed = _parse_question_block(
                SplitQuestionBlock(
                    raw_text=base_text,
                    question_no_override=block.question_no_override,
                    stem_prefix=block.stem_prefix,
                ),
                section,
            )
            entry = appendix_entries.get(_normalized_question_no(parsed.question_no))
            if entry is None:
                continue
            additions: list[str] = []
            if not (parsed.answer_text or "").strip() and (entry.answer_text or "").strip():
                additions.append(f"答案：{entry.answer_text.strip()}")
            if not (parsed.analysis_text or "").strip() and (entry.analysis_text or "").strip():
                additions.append(f"解析：{entry.analysis_text.strip()}")
            if additions:
                block.raw_text = f"{base_text.rstrip()}\n" + "\n".join(additions)
            else:
                block.raw_text = base_text
    return sections


def _extract_appendix_solution_entries(text: str) -> dict[str, AppendixSolutionEntry]:
    entries: dict[str, AppendixSolutionEntry] = {}
    for segment in _answer_appendix_segments(text):
        for entry in _parse_answer_appendix_segment(segment):
            key = _normalized_question_no(entry.question_no)
            if not key:
                continue
            current = entries.get(key)
            if current is None:
                entries[key] = entry
                continue
            if not current.answer_text and entry.answer_text:
                current.answer_text = entry.answer_text
            if not current.analysis_text and entry.analysis_text:
                current.analysis_text = entry.analysis_text
    return entries


def _strip_appendix_from_block(raw_text: str) -> str:
    if not raw_text:
        return raw_text
    if not ANSWER_ANALYSIS_HEADER_PATTERN.search(raw_text):
        return raw_text
    appendix_start = ANSWER_ANALYSIS_HEADER_PATTERN.search(raw_text)
    if appendix_start is None:
        return raw_text
    return raw_text[: appendix_start.start()].rstrip()


def _answer_appendix_segments(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    matches = list(ANSWER_ANALYSIS_HEADER_PATTERN.finditer(normalized))
    if not matches:
        return []
    segments: list[str] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        segment = normalized[start:end].strip()
        if segment:
            segments.append(segment)
    return segments


def _parse_answer_appendix_segment(segment: str) -> list[AppendixSolutionEntry]:
    pattern = re.compile(
        r"(?ms)^\s*(?:第\s*)?(?P<no>[0-9]{1,3}|[一二三四五六七八九十百]{1,6})\s*[\.、．)]?\s*(?P<body>.+?)(?=^\s*(?:第\s*)?(?:[0-9]{1,3}|[一二三四五六七八九十百]{1,6})\s*[\.、．)]?\s*|\Z)"
    )
    results: list[AppendixSolutionEntry] = []
    for match in pattern.finditer(segment):
        question_no = str(match.group("no") or "").strip()
        body = str(match.group("body") or "").strip()
        if not question_no or not body:
            continue
        answer_text, analysis_text = _extract_appendix_answer_analysis(body)
        if not answer_text and not analysis_text:
            continue
        results.append(
            AppendixSolutionEntry(
                question_no=question_no,
                answer_text=answer_text,
                analysis_text=analysis_text,
            )
        )
    return results


def _extract_appendix_answer_analysis(body: str) -> tuple[str | None, str | None]:
    answer_match = _find_earliest_match(ANSWER_HEADER_INLINE_PATTERNS, body)
    analysis_match = _find_earliest_match(ANALYSIS_HEADER_INLINE_PATTERNS, body)

    if answer_match is not None:
        answer_end = answer_match.end()
        answer_stop = analysis_match.start() if analysis_match and analysis_match.start() > answer_end else len(body)
        answer_text = _clean_solution_text(body[answer_end:answer_stop])
        analysis_text = _clean_solution_text(body[analysis_match.end() :]) if analysis_match else None
        return answer_text, analysis_text

    first_line, _, remainder = body.partition("\n")
    compact_first = re.sub(r"\s+", "", first_line).upper()
    if MULTI_ANSWER_PATTERN.match(compact_first) or re.fullmatch(r"[A-H]", compact_first) or JUDGE_ANSWER_PATTERN.match(compact_first):
        answer_text = first_line.strip() or None
        analysis_text = _clean_solution_text(remainder)
        return answer_text, analysis_text

    if analysis_match is not None:
        analysis_end = analysis_match.end()
        analysis_text = _clean_solution_text(body[analysis_end:])
        return None, analysis_text

    return None, None


def _normalized_question_no(value: str | None) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def _find_earliest_match(patterns: tuple[re.Pattern[str], ...], text: str) -> re.Match[str] | None:
    earliest: re.Match[str] | None = None
    for pattern in patterns:
        match = pattern.search(text)
        if match is None:
            continue
        if earliest is None or match.start() < earliest.start():
            earliest = match
    return earliest


def _clean_solution_text(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text or None


def _parse_question_block(block: SplitQuestionBlock, section: ParsedSection) -> ParsedQuestionBlock:
    from app.services.paper_parser_rules.engine import RuleBlock, RuleSection

    parsed = parse_rule_question_block(
        RuleBlock(
            raw_text=block.raw_text,
            question_no_override=block.question_no_override,
            stem_prefix=block.stem_prefix,
        ),
        RuleSection(
            title=section.title,
            section_type=section.section_type,
            sort_order=section.sort_order,
            blocks=[],
        ),
    )
    return ParsedQuestionBlock(
        question_no=parsed.question_no,
        question_type=parsed.question_type,
        stem_text=parsed.stem_text,
        options_json=parsed.options,
        answer_text=parsed.answer_text,
        analysis_text=parsed.analysis_text,
        difficulty_level=parsed.difficulty_level,
        quality_score=parsed.quality_score,
        subquestion_count=parsed.subquestion_count,
        source_section_name=parsed.source_section_name,
        quality_issues=parsed.quality_issues,
    )


def _make_question_uid(
    paper_id: int,
    section_id: int | None,
    question_index: int,
    parsed: ParsedQuestionBlock,
) -> str:
    uid_seed = f"{paper_id}:{section_id or 0}:{question_index}:{parsed.question_no}:{parsed.stem_text[:80]}"
    question_uid = hashlib.sha1(uid_seed.encode("utf-8")).hexdigest()[:24]
    return f"P{paper_id}-{question_uid}"


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
