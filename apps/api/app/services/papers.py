from __future__ import annotations

import hashlib
import re
from datetime import datetime
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException
from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Asset, ExamPaper, ExamQuestion, PaperSection, Subject
from app.repositories.papers import PaperRepository
from app.schemas.papers import (
    PaperDeleteResponse,
    PaperDetailResponse,
    PaperParseResponse,
    PaperSectionResponse,
    PaperSummary,
    PaperUploadResponse,
)
from app.services.tagging import apply_rule_tags
from library.parse_options import DocumentParseOptions
from library.parser import parse_document

PaperParseProgressCallback = Callable[[str, int, dict[str, object] | None], None]

ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".docx", ".md", ".txt"}
ALLOWED_UPLOAD_MIME_PREFIXES = ("application/", "image/", "text/")
QUESTION_SPLIT_PATTERN = re.compile(r"(?m)^\s*(?:第\s*)?([0-9]{1,3}|[一二三四五六七八九十百]{1,6})\s*[\.、．)]\s*")
OPTION_PATTERN = re.compile(r"(?m)^\s*([A-H])[\.\、．)]\s*(.+?)(?=(?:\n\s*[A-H][\.\、．)]\s*)|\Z)", re.S)
ANSWER_PATTERN = re.compile(r"(?:答案|参考答案|正确答案)\s*[:：]\s*(.+?)(?=(?:\n\s*(?:解析|答案解析|【解析】)\s*[:：])|\Z)", re.S)
ANALYSIS_PATTERN = re.compile(r"(?:解析|答案解析|【解析】)\s*[:：]\s*(.+)$", re.S)
SECTION_HEADER_PATTERN = re.compile(
    r"(?m)^\s*(?:(?:第\s*[一二三四五六七八九十百0-9]+\s*部分)|(?:[一二三四五六七八九十百0-9]+\s*[、.．]))?\s*"
    r"(?P<title>(?:单项选择题|多项选择题|判断题|填空题|简答题|计算题|案例分析题|综合题|材料分析题))"
    r"(?:\s*[（(][^)\n）]+[)）])?\s*$"
)
SUBQUESTION_PATTERN = re.compile(r"(?m)^\s*[(（]([1-9][0-9]{0,2}|[一二三四五六七八九十]+)[)）]\s*")
MULTI_ANSWER_PATTERN = re.compile(r"^[A-H](?:[\s,，/、]+[A-H])+$")
JUDGE_ANSWER_PATTERN = re.compile(r"^(?:正确|错误|对|错|√|×)$")
SECTION_TYPE_MAP = {
    "单项选择题": "single_choice",
    "多项选择题": "multiple_choice",
    "判断题": "judge",
    "填空题": "fill_blank",
    "简答题": "short_answer",
    "计算题": "calculation",
    "案例分析题": "case_analysis",
    "综合题": "composite",
    "材料分析题": "material_analysis",
}


@dataclass(slots=True)
class ParsedSection:
    title: str
    section_type: str
    sort_order: int
    blocks: list[str]


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
        sections = [PaperSectionResponse.model_validate(item) for item in self.repository.list_sections(paper.id)]
        return PaperDetailResponse.model_validate(
            {
                **paper.__dict__,
                "subject_name": subject.name if subject else None,
                "category": category.name if category else _category_from_asset_tags(asset.tags_json if asset else None),
                "asset_filename": asset.filename if asset else None,
                "asset_parse_status": asset.parse_status if asset else None,
                "sections": sections,
            }
        )

    def delete_paper(self, paper_id: int) -> PaperDeleteResponse:
        paper = self.repository.get_paper(paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="试卷不存在")
        paper_name = paper.paper_name
        removed_question_count = len(self.repository.list_questions(paper.id))
        removed_source_link_count = self.repository.count_source_links(paper.id)
        self.repository.delete_paper(paper.id)
        self.session.commit()
        return PaperDeleteResponse(
            id=paper_id,
            paper_name=paper_name,
            deleted=True,
            removed_question_count=removed_question_count,
            removed_source_link_count=removed_source_link_count,
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

        _emit_parse_progress(progress_callback, "read_file", 10, {"filename": asset.filename})
        data = storage_path.read_bytes()
        parsed_document = parse_document(
            data,
            asset.filename,
            asset.mime_type,
            options=options,
            progress_callback=progress_callback,
        )
        parsed_text = parsed_document.markdown or parsed_document.text
        if not parsed_text.strip():
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

        _emit_parse_progress(progress_callback, "split_questions", 76, {"text_length": len(parsed_text)})
        self.repository.delete_parse_outputs(paper.id)
        parsed_sections = _split_paper_sections(parsed_text)
        questions: list[ExamQuestion] = []
        created_sections: list[PaperSection] = []
        quality_warnings: list[str] = []
        subject_id = paper.subject_id
        if subject_id is None:
            subject_id = asset.subject_id
        if subject_id is None:
            first_subject = self.repository.list_knowledge_points(None)
            if first_subject:
                subject_id = first_subject[0].subject_id
        if subject_id is None:
            raise HTTPException(status_code=422, detail="试卷或素材必须绑定学科后才能切题")

        running_start_no: int | None = 1
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
            _emit_parse_progress(
                progress_callback,
                "build_sections",
                min(84, 76 + int((section_index / max(1, len(parsed_sections))) * 8)),
                {
                    "section_index": section_index,
                    "section_count": len(parsed_sections),
                    "section_name": parsed_section.title,
                },
            )

            section_questions: list[ExamQuestion] = []
            for block in parsed_section.blocks:
                parsed = _parse_question_block(block, parsed_section)
                if parsed.quality_issues:
                    quality_warnings.append(
                        f"{parsed_section.title} 第{parsed.question_no}题：{'；'.join(parsed.quality_issues)}"
                    )
                uid_seed = f"{paper.id}:{section.id}:{parsed.question_no}:{parsed.stem_text[:80]}"
                question_uid = hashlib.sha1(uid_seed.encode("utf-8")).hexdigest()[:24]
                section_questions.append(
                    ExamQuestion(
                        tenant_id=paper.tenant_id,
                        paper_id=paper.id,
                        subject_id=subject_id,
                        section_id=section.id,
                        question_no=parsed.question_no,
                        question_uid=f"P{paper.id}-{question_uid}",
                        question_type=parsed.question_type,
                        stem_text=parsed.stem_text,
                        options_json=parsed.options_json,
                        answer_text=parsed.answer_text,
                        analysis_text=parsed.analysis_text,
                        source_page_from=None,
                        source_page_to=None,
                        score=None,
                        difficulty_level=parsed.difficulty_level,
                        quality_score=parsed.quality_score,
                        is_duplicate=False,
                        duplicate_group_id=None,
                        parse_status="needs_review" if parsed.quality_issues else "parsed",
                        review_status="needs_review" if parsed.quality_issues else "pending",
                        review_note="；".join(parsed.quality_issues) if parsed.quality_issues else None,
                        created_by=operator_id,
                        updated_by=operator_id,
                    )
                )

            if section_questions:
                section.start_no = running_start_no
                running_start_no = (running_start_no or 1) + len(section_questions)
                section.end_no = (running_start_no - 1) if running_start_no else None
            section.question_type = _merge_section_question_type(parsed_section.section_type, section_questions)
            questions.extend(section_questions)

        quality_warnings.extend(_collect_numbering_warnings(questions))
        self.repository.create_questions(questions)
        _emit_parse_progress(progress_callback, "tagging", 88, {"question_count": len(questions)})
        points = self.repository.list_knowledge_points(subject_id)
        tagged_count = 0
        for question_index, question in enumerate(questions, start=1):
            tagged_count += len(apply_rule_tags(self.session, question, points, paper.tenant_id, operator_id))
            if question_index == len(questions) or question_index % 10 == 0:
                _emit_parse_progress(
                    progress_callback,
                    "tagging",
                    min(96, 88 + int((question_index / max(1, len(questions))) * 8)),
                    {"tagged_questions": question_index, "question_count": len(questions)},
                )

        asset.parsed_text = parsed_text
        asset.token_count = max(1, len(parsed_text) // 2)
        asset.parse_status = "parsed"
        asset.ocr_status = "completed"
        paper.status = "parsed"
        paper.total_question_count = len(questions)
        paper.review_status = "pending"
        _emit_parse_progress(progress_callback, "saving", 98, {"question_count": len(questions)})
        self.session.commit()
        _emit_parse_progress(progress_callback, "completed", 100, {"question_count": len(questions)})
        return PaperParseResponse(
            paper_id=paper.id,
            asset_id=asset.id,
            parse_status=asset.parse_status,
            paper_status=paper.status,
            question_count=len(questions),
            section_count=len([section for section in created_sections if section.start_no is not None]),
            tagged_count=tagged_count,
            preview=parsed_text[:300],
            provider=parsed_document.provider,
            warnings=[*parsed_document.warnings, *quality_warnings][:10],
            parse_options=options.normalized_dump(),
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
        existing_asset = self.repository.get_asset_by_sha(sha256)
        if existing_asset:
            if subject and existing_asset.subject_id != subject.id:
                existing_asset.subject_id = subject.id
            if normalized_category:
                existing_tags = [
                    tag
                    for tag in existing_asset.tags_json or []
                    if not (isinstance(tag, str) and tag.startswith("category:"))
                ]
                existing_tags.append(f"category:{normalized_category}")
                existing_asset.tags_json = existing_tags
            existing_paper = self.repository.get_paper_by_asset(existing_asset.id)
            if existing_paper:
                if subject and existing_paper.subject_id != subject.id:
                    existing_paper.subject_id = subject.id
                if subject_category:
                    existing_paper.category_id = subject_category.id
                self.session.commit()
                return self._upload_response(existing_paper, existing_asset)
            asset = existing_asset
        else:
            yyyymm = datetime.utcnow().strftime("%Y%m")
            storage_key = f"papers/{yyyymm}/{sha256}{suffix}"
            storage_path = settings.storage.root_path / storage_key
            storage_path.parent.mkdir(parents=True, exist_ok=True)
            if not storage_path.exists():
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


def _split_question_blocks(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    matches = list(QUESTION_SPLIT_PATTERN.finditer(normalized))
    blocks: list[str] = []
    if not matches:
        chunks = [chunk.strip() for chunk in re.split(r"\n{2,}", normalized) if chunk.strip()]
        return chunks[:80] if chunks else [normalized.strip()]

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        block = normalized[match.start():end].strip()
        if block:
            blocks.append(block)
    return blocks[:200]


def _split_paper_sections(text: str) -> list[ParsedSection]:
    normalized = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    matches = list(SECTION_HEADER_PATTERN.finditer(normalized))
    sections: list[ParsedSection] = []

    if not matches:
        blocks = _split_question_blocks(normalized)
        return [ParsedSection(title="自动切题", section_type="mixed", sort_order=1, blocks=blocks)]

    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        body = normalized[start:end].strip()
        title = match.group("title").strip()
        blocks = _split_question_blocks(body) if body else []
        if not blocks:
            continue
        sections.append(
            ParsedSection(
                title=title,
                section_type=SECTION_TYPE_MAP.get(title, "mixed"),
                sort_order=len(sections) + 1,
                blocks=blocks,
            )
        )

    if sections:
        return sections

    blocks = _split_question_blocks(normalized)
    return [ParsedSection(title="自动切题", section_type="mixed", sort_order=1, blocks=blocks)]


def _parse_question_block(block: str, section: ParsedSection) -> ParsedQuestionBlock:
    block = block.strip()
    number_match = QUESTION_SPLIT_PATTERN.match(block)
    question_no = number_match.group(1) if number_match else str(section.sort_order)
    content = block[number_match.end():].strip() if number_match else block

    answer_text = _extract_pattern(ANSWER_PATTERN, content)
    analysis_text = _extract_pattern(ANALYSIS_PATTERN, content)
    content_without_answer = ANSWER_PATTERN.sub("", content).strip()
    content_without_answer = ANALYSIS_PATTERN.sub("", content_without_answer).strip()

    options = [f"{match.group(1)}. {match.group(2).strip()}" for match in OPTION_PATTERN.finditer(content_without_answer)]
    stem = OPTION_PATTERN.sub("", content_without_answer).strip()
    stem = re.sub(r"\n{3,}", "\n\n", stem)
    subquestion_count = len(SUBQUESTION_PATTERN.findall(content_without_answer))
    question_type = _detect_question_type(section.section_type, options, answer_text, content_without_answer, subquestion_count)
    quality_score = _estimate_quality_score(stem, options, answer_text, analysis_text, subquestion_count, section.section_type)
    quality_issues = _collect_quality_issues(
        question_type=question_type,
        stem=stem,
        options=options,
        answer_text=answer_text,
        analysis_text=analysis_text,
        quality_score=quality_score,
    )
    difficulty = _estimate_difficulty(question_type, subquestion_count)
    return ParsedQuestionBlock(
        question_no=str(question_no),
        question_type=question_type,
        stem_text=stem or content[:500] or f"第 {question_no} 题",
        options_json=options,
        answer_text=answer_text,
        analysis_text=analysis_text,
        difficulty_level=difficulty,
        quality_score=quality_score,
        subquestion_count=subquestion_count,
        source_section_name=section.title,
        quality_issues=quality_issues,
    )


def _detect_question_type(
    section_type: str,
    options: list[str],
    answer_text: str | None,
    content_without_answer: str,
    subquestion_count: int,
) -> str:
    normalized_answer = re.sub(r"\s+", " ", answer_text or "").strip().upper()
    if section_type != "mixed":
      return section_type
    if len(options) >= 2 and normalized_answer and MULTI_ANSWER_PATTERN.match(normalized_answer):
        return "multiple_choice"
    if len(options) >= 2:
        return "single_choice"
    if normalized_answer and JUDGE_ANSWER_PATTERN.match(normalized_answer):
        return "judge"
    if subquestion_count >= 2:
        return "case_analysis"
    if "计算" in content_without_answer[:30]:
        return "calculation"
    if "材料" in content_without_answer[:40] or "阅读下列" in content_without_answer[:40]:
        return "material_analysis"
    if re.search(r"[_＿]{2,}", content_without_answer):
        return "fill_blank"
    return "short_answer"


def _estimate_quality_score(
    stem: str,
    options: list[str],
    answer_text: str | None,
    analysis_text: str | None,
    subquestion_count: int,
    section_type: str,
) -> float:
    score = 0.45
    if stem:
        score += 0.18
    if options:
        score += 0.12
    if answer_text:
        score += 0.1
    if analysis_text:
        score += 0.08
    if subquestion_count:
        score += min(0.08, subquestion_count * 0.02)
    if section_type != "mixed":
        score += 0.05
    return round(min(score, 0.96), 2)


def _collect_quality_issues(
    *,
    question_type: str,
    stem: str,
    options: list[str],
    answer_text: str | None,
    analysis_text: str | None,
    quality_score: float,
) -> list[str]:
    issues: list[str] = []
    if len(stem.strip()) < 8:
        issues.append("题干过短或缺失")
    if question_type in {"single_choice", "multiple_choice"}:
        option_labels = {option[:1].upper() for option in options if option}
        expected = {"A", "B", "C", "D"}
        missing = sorted(expected - option_labels)
        if missing:
            issues.append(f"选项缺失：{','.join(missing)}")
        if answer_text:
            answer_letters = set(re.findall(r"[A-H]", answer_text.upper()))
            if answer_letters and not answer_letters.issubset(option_labels):
                issues.append("答案选项与识别选项不匹配")
        else:
            issues.append("答案缺失")
    elif not answer_text:
        issues.append("答案缺失")
    if not analysis_text:
        issues.append("解析缺失")
    if quality_score < 0.72:
        issues.append("结构化质量分偏低")
    return issues[:6]


def _collect_numbering_warnings(questions: list[ExamQuestion]) -> list[str]:
    numeric_numbers = []
    for question in questions:
        try:
            numeric_numbers.append(int(str(question.question_no)))
        except ValueError:
            continue
    if len(numeric_numbers) < 2:
        return []
    expected = list(range(min(numeric_numbers), max(numeric_numbers) + 1))
    missing = sorted(set(expected) - set(numeric_numbers))
    duplicates = sorted({number for number in numeric_numbers if numeric_numbers.count(number) > 1})
    warnings: list[str] = []
    if missing:
        warnings.append(f"题号不连续，缺少：{','.join(str(item) for item in missing[:20])}")
    if duplicates:
        warnings.append(f"题号重复：{','.join(str(item) for item in duplicates[:20])}")
    return warnings


def _estimate_difficulty(question_type: str, subquestion_count: int) -> int:
    if question_type in {"single_choice", "judge"}:
        return 2
    if question_type in {"multiple_choice", "fill_blank", "short_answer"}:
        return 3
    if question_type in {"calculation", "case_analysis", "material_analysis", "composite"}:
        return 4 if subquestion_count >= 2 else 3
    return 3


def _merge_section_question_type(default_type: str, questions: list[ExamQuestion]) -> str:
    if not questions:
        return default_type
    if default_type != "mixed":
        return default_type
    first_type = questions[0].question_type
    if any(question.question_type != first_type for question in questions):
        return "mixed"
    return first_type


def _extract_pattern(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip() or None


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
