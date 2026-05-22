from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from library.trained_ocr_cleaner import should_drop_line


_ZERO_WIDTH_PATTERN = re.compile(r"[\u200b-\u200f\u202a-\u202e\ufeff]")
_CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_CIRCLED_NUMBER_PATTERN = re.compile(
    "["
    "\u2460-\u2473"  # circled 1-20
    "\u24ea\u24f5-\u24ff"  # circled/double-circled 0-10
    "\u2776-\u2793"  # dingbat circled 1-10 variants
    "\u3251-\u325f"  # circled 21-35
    "\u32b1-\u32bf"  # circled 36-50
    "]"
)
_PAGE_NUMBER_PATTERN = re.compile(r"^(?:第\s*)?\d+\s*(?:页|頁|/+\s*\d+)?$")
_PAGE_X_OF_Y_PATTERN = re.compile(r"^(?:page\s*)?\d+\s*/\s*\d+$", re.IGNORECASE)
_DIGIT_ONLY_PATTERN = re.compile(r"^\d{1,3}$")
_SYMBOL_ONLY_PATTERN = re.compile(r"^[\s\-_=~·•⋅…—–_（）(){}[\]<>【】《》。、，,.:：;；|/\\]+$")
_QUESTION_START_PATTERN = re.compile(r"^\s*(?:#+\s*)?(?:第\s*)?(?:\d{1,3}|[一二三四五六七八九十百]{1,6})\s*(?:题|[\.、．)])\s*")
_SECTION_HEADER_PATTERN = re.compile(
    r"^\s*(?:#+\s*)?(?:第\s*[一二三四五六七八九十百0-9]+\s*部分\s*)?"
    r"(单项选择题|多项选择题|不定项选择题|判断题|填空题|简答题|计算题|案例分析题|综合题|材料分析题)\s*$"
)
_OPTION_LABEL_PATTERN = re.compile(r"([A-H])[\.\、．)]\s*")
_OPTION_LINE_PATTERN = re.compile(r"^\s*[A-H][\.\、．)]\s*")
_ACCOUNTING_ENTRY_PATTERN = re.compile(r"^\s*(?:借|贷)\s*[:：]")
_ANSWER_INLINE_PATTERN = re.compile(r"(?:答案|参考答案|正确答案)\s*[:：]\s*")
_ANALYSIS_INLINE_PATTERN = re.compile(r"(?:解析|答案解析|【解析】)\s*[:：]?\s*")
_ANSWER_HEADER_PATTERN = re.compile(r"^\s*(?:#+\s*)?(?:答案|参考答案|正确答案)\s*[:：]\s*", re.IGNORECASE)
_ANALYSIS_HEADER_PATTERN = re.compile(r"^\s*(?:#+\s*)?(?:解析|答案解析|【解析】)\s*(?:[:：]\s*|\n+)", re.IGNORECASE)
_OPTION_PREFIX_PATTERN = re.compile(r"^[A-H][\.\、．)]\s*")
_INLINE_QUESTION_START_PATTERN = re.compile(
    r"(?<!^)(?<!\d)(?:第\s*)?(?:\d{1,3}|[一二三四五六七八九十百]{1,6})\s*(?:题|[\.、．)])\s*(?=\S)"
)
_NOISE_HINTS = ("二维码", "公众号", "微信", "扫一扫", "扫描", "内部资料", "仅供参考", "版权所有")


@dataclass(slots=True)
class OCRCleanupReport:
    applied: bool = False
    input_chars: int = 0
    output_chars: int = 0
    input_lines: int = 0
    output_lines: int = 0
    removed_lines: int = 0
    merged_lines: int = 0
    split_lines: int = 0
    repeated_noise_lines: int = 0
    quality_score: float = 0.0
    reason_counts: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class _PageInput:
    page_number: int
    width: float = 0.0
    height: float = 0.0
    text_lines: list[str] = field(default_factory=list)
    markdown_lines: list[str] = field(default_factory=list)
    source_blocks: list[Any] = field(default_factory=list)


def clean_parsed_document(document: Any, *, force: bool = False) -> Any:
    if document is None:
        return document

    _ensure_raw_snapshot(document)

    cleanup_report = getattr(document, "cleanup_report", None)
    if cleanup_report and not force:
        return document

    provider = str(getattr(document, "provider", "") or "").lower()
    used_ocr = bool(getattr(document, "used_ocr", False))
    if not force and not _should_clean(provider, used_ocr):
        return document

    from library.parser import ParsedBlock, ParsedDocument, ParsedPage

    pages = _build_page_inputs(document)
    if not pages:
        text = _normalize_text(str(getattr(document, "text", "") or ""))
        markdown = _normalize_text(str(getattr(document, "markdown", "") or "")) or text
        if not text and not markdown:
            return document
        pages = [
            _PageInput(
                page_number=1,
                text_lines=_split_lines(text or markdown),
                markdown_lines=_split_lines(markdown or text),
            )
        ]

    repeated_noise = _detect_repeated_noise(pages)
    cleaned_pages: list[ParsedPage] = []
    cleaned_text_parts: list[str] = []
    cleaned_markdown_parts: list[str] = []
    report = OCRCleanupReport(applied=True)
    report.input_chars = len(str(getattr(document, "text", "") or "")) + len(str(getattr(document, "markdown", "") or ""))
    report.input_lines = sum(len(page.text_lines) or len(page.markdown_lines) for page in pages)
    report.repeated_noise_lines = len(repeated_noise)

    for page in pages:
        text_lines = _clean_lines(page.text_lines, repeated_noise, report, preserve_markdown=False)
        markdown_lines = _clean_lines(
            page.markdown_lines,
            repeated_noise,
            report,
            preserve_markdown=True,
            record_stats=False,
        )
        if not markdown_lines:
            markdown_lines = list(text_lines)

        text = "\n".join(text_lines).strip()
        markdown = "\n".join(markdown_lines).strip() or text
        blocks = [
            ParsedBlock(
                page_number=page.page_number,
                block_id=f"p{page.page_number}-clean-{index}",
                text=line,
            )
            for index, line in enumerate(text_lines, start=1)
        ]
        cleaned_pages.append(
            ParsedPage(
                page_number=page.page_number,
                width=page.width,
                height=page.height,
                text=text,
                markdown=markdown,
                blocks=blocks,
            )
        )
        if text:
            cleaned_text_parts.append(text)
        if markdown:
            cleaned_markdown_parts.append(markdown)

    cleaned_text = "\n\n".join(part for part in cleaned_text_parts if part).strip()
    cleaned_markdown = "\n\n".join(part for part in cleaned_markdown_parts if part).strip() or cleaned_text
    report.output_chars = len(cleaned_text) + len(cleaned_markdown)
    report.output_lines = sum(len(page.text.splitlines()) for page in cleaned_pages if page.text)
    report.quality_score = _estimate_quality_score(cleaned_text, report)

    warnings = [str(item) for item in getattr(document, "warnings", []) or [] if str(item).strip()]
    if report.notes:
        warnings.extend(report.notes)

    return ParsedDocument(
        text=cleaned_text or str(getattr(document, "text", "") or ""),
        markdown=cleaned_markdown or str(getattr(document, "markdown", "") or cleaned_text),
        provider=str(getattr(document, "provider", "") or "unknown"),
        used_ocr=used_ocr,
        pages=cleaned_pages,
        tables=list(getattr(document, "tables", []) or []),
        warnings=warnings[:20],
        cleanup_report=report.to_dict(),
        cleanup_score=report.quality_score,
        raw_text=str(getattr(document, "raw_text", "") or getattr(document, "text", "") or ""),
        raw_markdown=str(getattr(document, "raw_markdown", "") or getattr(document, "markdown", "") or ""),
        markdown_image_roots=list(getattr(document, "markdown_image_roots", []) or []),
    )


def _should_clean(provider: str, used_ocr: bool) -> bool:
    return used_ocr or any(marker in provider for marker in ("ocr", "structure", "rapidocr", "paddle"))


def _ensure_raw_snapshot(document: Any) -> None:
    if getattr(document, "raw_text", None) in {None, ""}:
        try:
            document.raw_text = str(getattr(document, "text", "") or "")
        except Exception:
            pass
    if getattr(document, "raw_markdown", None) in {None, ""}:
        try:
            document.raw_markdown = str(getattr(document, "markdown", "") or getattr(document, "text", "") or "")
        except Exception:
            pass


def raw_document_snapshot(document: Any) -> dict[str, Any]:
    _ensure_raw_snapshot(document)
    return {
        "raw_text": str(getattr(document, "raw_text", "") or getattr(document, "text", "") or ""),
        "raw_markdown": str(getattr(document, "raw_markdown", "") or getattr(document, "markdown", "") or ""),
    }


def maybe_clean_parsed_document(
    document: Any,
    *,
    raw_ocr_mode: bool = False,
    force: bool = False,
) -> Any:
    if document is None:
        return document
    provider = str(getattr(document, "provider", "") or "").lower()
    used_ocr = bool(getattr(document, "used_ocr", False))
    if raw_ocr_mode and _should_clean(provider, used_ocr):
        return _prepare_raw_ocr_document(document)
    return clean_parsed_document(document, force=force)


def _prepare_raw_ocr_document(document: Any) -> Any:
    snapshot = raw_document_snapshot(document)
    restored_text = snapshot["raw_text"]
    restored_markdown = snapshot["raw_markdown"] or restored_text
    for field_name, value in (
        ("text", restored_text),
        ("markdown", restored_markdown),
        ("raw_text", restored_text),
        ("raw_markdown", restored_markdown),
        ("cleanup_report", {}),
        ("cleanup_score", None),
    ):
        try:
            setattr(document, field_name, value)
        except Exception:
            continue
    return document


def _build_page_inputs(document: Any) -> list[_PageInput]:
    pages: list[_PageInput] = []
    raw_pages = list(getattr(document, "pages", []) or [])
    for page in raw_pages:
        page_number = int(getattr(page, "page_number", len(pages) + 1) or len(pages) + 1)
        width = float(getattr(page, "width", 0.0) or 0.0)
        height = float(getattr(page, "height", 0.0) or 0.0)
        text_lines: list[str] = []
        markdown_lines: list[str] = []
        blocks = list(getattr(page, "blocks", []) or [])
        if blocks:
            sortable_blocks = _sorted_blocks(blocks)
            for block in sortable_blocks:
                raw_text = str(getattr(block, "latex", None) or getattr(block, "text", "") or "").strip()
                if not raw_text:
                    continue
                text_lines.extend(_split_lines(raw_text))
                markdown_lines.extend(_split_lines(raw_text))
        else:
            text = str(getattr(page, "text", "") or "")
            markdown = str(getattr(page, "markdown", "") or "")
            text_lines.extend(_split_lines(text))
            markdown_lines.extend(_split_lines(markdown or text))
        pages.append(
            _PageInput(
                page_number=page_number,
                width=width,
                height=height,
                text_lines=text_lines,
                markdown_lines=markdown_lines,
                source_blocks=blocks,
            )
        )
    return pages


def _sorted_blocks(blocks: list[Any]) -> list[Any]:
    if any(len(getattr(block, "bbox", None) or []) == 4 for block in blocks):
        return sorted(blocks, key=_block_sort_key)
    return list(blocks)


def _block_sort_key(block: Any) -> tuple[float, float, str]:
    bbox = getattr(block, "bbox", None) or []
    if len(bbox) == 4:
        return float(bbox[1]), float(bbox[0]), str(getattr(block, "block_id", ""))
    return 1e9, 1e9, str(getattr(block, "block_id", ""))


def _split_lines(text: str) -> list[str]:
    if not text:
        return []
    normalized = _normalize_text(text)
    return [line for line in normalized.splitlines() if line.strip()]


def _clean_lines(
    lines: list[str],
    repeated_noise: set[str],
    report: OCRCleanupReport,
    *,
    preserve_markdown: bool,
    record_stats: bool = True,
) -> list[str]:
    if not lines:
        return []

    cleaned: list[str] = []
    for index, raw_line in enumerate(lines):
        normalized = _normalize_line(raw_line, preserve_markdown=preserve_markdown)
        if not normalized:
            continue
        normalized = _trim_noise_prefix(normalized)
        if _should_keep_numeric_line(normalized, cleaned, lines, index, preserve_markdown=preserve_markdown):
            if cleaned and _should_merge(cleaned[-1], normalized):
                cleaned[-1] = f"{cleaned[-1]} {normalized}".strip()
                if record_stats:
                    report.merged_lines += 1
                    report.reason_counts["merged"] = report.reason_counts.get("merged", 0) + 1
                continue
            cleaned.append(normalized)
            continue
        if _is_noise_line(normalized, repeated_noise):
            if record_stats:
                report.removed_lines += 1
                reason = _noise_reason(normalized, repeated_noise)
                report.reason_counts[reason] = report.reason_counts.get(reason, 0) + 1
            continue
        expanded = _expand_structural_line(normalized)
        if record_stats and len(expanded) > 1:
            report.split_lines += len(expanded) - 1
        for item in expanded:
            if not item:
                continue
            if cleaned and _should_merge(cleaned[-1], item):
                cleaned[-1] = f"{cleaned[-1]} {item}".strip()
                if record_stats:
                    report.merged_lines += 1
                    report.reason_counts["merged"] = report.reason_counts.get("merged", 0) + 1
                continue
            cleaned.append(item)
    return cleaned


def _normalize_text(text: str) -> str:
    value = text.replace("\ufeff", "")
    value = _ZERO_WIDTH_PATTERN.sub("", value)
    value = _CONTROL_PATTERN.sub(" ", value)
    value, protected_circled_numbers = _protect_circled_numbers(value)
    value = unicodedata.normalize("NFKC", value)
    value = _restore_protected_circled_numbers(value, protected_circled_numbers)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _protect_circled_numbers(text: str) -> tuple[str, list[str]]:
    protected: list[str] = []

    def replace(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"\ue000OCR_CIRCLED_NUMBER_{len(protected) - 1}\ue001"

    return _CIRCLED_NUMBER_PATTERN.sub(replace, text), protected


def _restore_protected_circled_numbers(text: str, protected: list[str]) -> str:
    for index, value in enumerate(protected):
        text = text.replace(f"\ue000OCR_CIRCLED_NUMBER_{index}\ue001", value)
    return text


def _normalize_line(line: str, *, preserve_markdown: bool) -> str:
    value = _normalize_text(line)
    if not value:
        return ""
    value = re.sub(r"^(?:>\s*)+", "", value).strip()
    if preserve_markdown:
        match = re.match(r"^(\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+))(.+)$", value)
        if match:
            prefix = match.group(1)
            body = re.sub(r"\s+", " ", match.group(2)).strip()
            return f"{prefix}{body}".strip()
    return re.sub(r"\s+", " ", value).strip()


def _detect_repeated_noise(pages: list[_PageInput]) -> set[str]:
    hits: Counter[str] = Counter()
    page_hits: dict[str, set[int]] = {}
    for page in pages:
        for line in page.text_lines:
            key = _noise_key(line)
            if not key:
                continue
            hits[key] += 1
            page_hits.setdefault(key, set()).add(page.page_number)
    return {
        key
        for key, count in hits.items()
        if count >= 2 and len(page_hits.get(key, set())) >= 2 and len(key) <= 80 and not _is_high_signal(key)
    }


def _noise_key(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip())
    normalized = re.sub(r"\d+", "#", normalized)
    normalized = re.sub(r"^[>#\-\*\s]+", "", normalized)
    return normalized


def _trim_noise_prefix(text: str) -> str:
    for marker in ("答案：", "答案:", "解析：", "解析:", "借：", "借:", "贷：", "贷:"):
        index = text.find(marker)
        if index <= 0:
            continue
        prefix = text[:index].strip()
        if _looks_like_noise_prefix(prefix):
            return text[index:].strip()
    return text


def _looks_like_noise_prefix(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text.strip())
    if not normalized:
        return False
    if _OPTION_PREFIX_PATTERN.match(text.strip()):
        return False
    if _SYMBOL_ONLY_PATTERN.match(normalized):
        return True
    if any(hint in normalized for hint in _NOISE_HINTS):
        return True
    if "http" in normalized.lower() or "www." in normalized.lower():
        return True
    return len(normalized) <= 12 and len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", normalized)) <= 4


def _should_keep_numeric_line(
    line: str,
    cleaned: list[str],
    lines: list[str],
    index: int,
    *,
    preserve_markdown: bool,
) -> bool:
    compact = re.sub(r"\s+", "", line)
    if not compact.isdigit() or len(compact) > 3:
        return False
    if cleaned and _ACCOUNTING_ENTRY_PATTERN.match(cleaned[-1]):
        return True
    for raw_line in lines[index + 1 :]:
        lookahead = _normalize_line(raw_line, preserve_markdown=preserve_markdown)
        if not lookahead:
            continue
        return bool(_ACCOUNTING_ENTRY_PATTERN.match(lookahead))
    return False


def _is_noise_line(text: str, repeated_noise: set[str]) -> bool:
    key = _noise_key(text)
    if key in repeated_noise:
        return True
    normalized = text.strip()
    if not normalized:
        return True
    if _is_high_signal(normalized):
        return False
    if _ACCOUNTING_ENTRY_PATTERN.match(normalized):
        return False
    if _PAGE_NUMBER_PATTERN.match(normalized) or _PAGE_X_OF_Y_PATTERN.match(normalized) or _DIGIT_ONLY_PATTERN.match(normalized):
        return True
    if _SYMBOL_ONLY_PATTERN.match(normalized):
        return True
    if any(hint in normalized for hint in _NOISE_HINTS):
        return True
    if should_drop_line(normalized):
        return True
    if normalized.isdigit() and len(normalized) > 1:
        return False
    if len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", normalized)) <= 1 and len(normalized) <= 8:
        return True
    return False


def _noise_reason(text: str, repeated_noise: set[str]) -> str:
    key = _noise_key(text)
    if key in repeated_noise:
        return "repeated_noise"
    if _PAGE_NUMBER_PATTERN.match(text) or _PAGE_X_OF_Y_PATTERN.match(text) or _DIGIT_ONLY_PATTERN.match(text):
        return "page_number"
    if _SYMBOL_ONLY_PATTERN.match(text):
        return "symbols"
    if any(hint in text for hint in _NOISE_HINTS):
        return "hint"
    return "noise"


def _is_high_signal(text: str) -> bool:
    return bool(
        _QUESTION_START_PATTERN.match(text)
        or _SECTION_HEADER_PATTERN.match(text)
        or _OPTION_LINE_PATTERN.match(text)
        or len(_OPTION_LABEL_PATTERN.findall(text)) >= 2
        or _ANSWER_HEADER_PATTERN.match(text)
        or _ANALYSIS_HEADER_PATTERN.match(text)
        or "答案" in text
        or "解析" in text
    )


def _expand_structural_line(text: str) -> list[str]:
    question_segments = _split_inline_question_segments(text)
    if len(question_segments) > 1:
        expanded: list[str] = []
        for segment in question_segments:
            expanded.extend(_expand_structural_line(segment))
        return [item for item in expanded if item]

    answer_match = _ANSWER_INLINE_PATTERN.search(text)
    analysis_match = _ANALYSIS_INLINE_PATTERN.search(text)
    solution_start: int | None = None
    if answer_match and analysis_match:
        solution_start = min(answer_match.start(), analysis_match.start())
    elif answer_match:
        solution_start = answer_match.start()
    elif analysis_match:
        solution_start = analysis_match.start()

    if solution_start is None:
        return _split_question_with_inline_options(text)

    question_part = text[:solution_start].strip()
    solution_part = text[solution_start:].strip()
    parts = _split_question_with_inline_options(question_part)
    if solution_part:
        parts.extend(_split_solution_segments(solution_part))
    return [item for item in parts if item] or [text]


def _split_inline_question_segments(text: str) -> list[str]:
    current = text.strip()
    if not current:
        return []

    parts: list[str] = []
    while current:
        match = _find_inline_question_boundary(current)
        if match is None:
            parts.append(current.strip())
            break
        prefix = current[: match.start()].strip()
        suffix = current[match.start() :].strip()
        if prefix:
            parts.append(prefix)
        current = suffix
    return [part for part in parts if part]


def _find_inline_question_boundary(text: str) -> re.Match[str] | None:
    for match in _INLINE_QUESTION_START_PATTERN.finditer(text):
        prefix = text[: match.start()].strip()
        suffix = text[match.start() :].strip()
        if _is_inline_question_boundary(prefix, suffix):
            return match
    return None


def _is_inline_question_boundary(prefix: str, suffix: str) -> bool:
    if not prefix or not suffix:
        return False
    match = _QUESTION_START_PATTERN.match(suffix)
    if match is None:
        return False
    body = suffix[match.end() :].strip()
    if len(body) < 2 or _looks_like_numeric_fragment(body):
        return False
    if _SECTION_HEADER_PATTERN.match(prefix):
        return True
    if _OPTION_LINE_PATTERN.match(prefix):
        return True
    if len(_OPTION_LABEL_PATTERN.findall(prefix)) >= 2:
        return True
    if _ANSWER_INLINE_PATTERN.search(prefix) or _ANALYSIS_INLINE_PATTERN.search(prefix):
        return True
    if prefix.endswith(("。", "！", "？", "；", ";", ")", "）", "]", "】")):
        return True
    return False


def _split_dense_option_line(line: str) -> list[str]:
    matches = list(_OPTION_LABEL_PATTERN.finditer(line))
    if len(matches) < 2:
        return [line]
    if not _looks_like_option_run(line, matches):
        return [line]

    pieces: list[str] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
        option_text = re.sub(r"\s+", " ", line[match.end() : end]).strip()
        if option_text:
            pieces.append(f"{match.group(1).upper()}. {option_text}")
    return pieces or [line]


def _split_question_with_inline_options(line: str) -> list[str]:
    matches = list(_OPTION_LABEL_PATTERN.finditer(line))
    if len(matches) < 2:
        return [line] if line else []
    if not _looks_like_option_run(line, matches):
        return [line] if line else []

    stem = re.sub(r"\s+", " ", line[: matches[0].start()]).strip()
    options = _split_dense_option_line(line[matches[0].start() :])
    parts = [item for item in ([stem] if stem else []) + options if item]
    return parts or [line]


def _split_solution_segments(text: str) -> list[str]:
    segments: list[str] = []
    answer_match = _ANSWER_INLINE_PATTERN.search(text) or _ANSWER_HEADER_PATTERN.search(text)
    analysis_match = _ANALYSIS_INLINE_PATTERN.search(text) or _ANALYSIS_HEADER_PATTERN.search(text)
    if answer_match and analysis_match and answer_match.start() <= analysis_match.start():
        answer = text[answer_match.start() : analysis_match.start()].strip()
        analysis = text[analysis_match.start() :].strip()
        if answer:
            segments.append(answer)
        if analysis:
            segments.append(analysis)
        return segments
    if answer_match:
        answer = text[answer_match.start() :].strip()
        if answer:
            segments.append(answer)
        return segments
    if analysis_match:
        analysis = text[analysis_match.start() :].strip()
        if analysis:
            segments.append(analysis)
        return segments
    return [text] if text else []


def _looks_like_option_run(line: str, matches: list[re.Match[str]]) -> bool:
    if len(matches) < 2:
        return False
    first = matches[0]
    if first.group(1).upper() != "A":
        return False
    stem = line[: first.start()].strip()
    if stem and "下列" not in stem and "的是" not in stem and "正确" not in stem and "属于" not in stem:
        return False
    labels: list[str] = []
    for match in matches:
        label = match.group(1).upper()
        if label not in labels:
            labels.append(label)
    return len(labels) >= 2 and labels[:2] == ["A", "B"]


def _should_merge(previous: str, current: str) -> bool:
    if not previous or not current:
        return False
    if _QUESTION_START_PATTERN.match(current) or _SECTION_HEADER_PATTERN.match(current):
        return False
    if _ACCOUNTING_ENTRY_PATTERN.match(previous) or _ACCOUNTING_ENTRY_PATTERN.match(current):
        return False
    if _OPTION_LINE_PATTERN.match(previous) or _OPTION_LINE_PATTERN.match(current):
        return False
    if _ANSWER_HEADER_PATTERN.match(previous) or _ANSWER_HEADER_PATTERN.match(current):
        return False
    if _ANALYSIS_HEADER_PATTERN.match(previous) or _ANALYSIS_HEADER_PATTERN.match(current):
        return False
    if _is_numeric_amount_line(previous) or _is_numeric_amount_line(current):
        return False
    if len(previous) > 64 and previous.endswith(("。", "！", "？", ")", "）")):
        return False
    if _looks_like_wrapped_text_line(previous, current):
        return True
    return len(previous) <= 32 or previous.endswith(("：", ":", "，", ",", "（", "(", "、"))


def _is_numeric_amount_line(text: str) -> bool:
    compact = re.sub(r"\s+", "", text.strip())
    return compact.isdigit() and 1 <= len(compact) <= 3


def _looks_like_wrapped_text_line(previous: str, current: str) -> bool:
    if len(previous) < 18 or len(current) < 2:
        return False
    if previous.endswith(("。", "！", "？", "；", ";")):
        return False
    if current.startswith(("答案", "解析", "正确答案", "参考答案")):
        return False
    if _looks_like_numeric_fragment(previous) or _looks_like_numeric_fragment(current):
        return False
    signal_chars = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", current)
    if len(signal_chars) < 2:
        return False
    if re.match(r"^[，,。．、；;：:）)\]】%]", current):
        return True
    if re.search(r"[\u4e00-\u9fffA-Za-z0-9]$", previous) and re.match(r"^[\u4e00-\u9fffA-Za-z0-9]", current):
        return True
    return False


def _looks_like_numeric_fragment(text: str) -> bool:
    compact = re.sub(r"\s+", "", text.strip())
    if not compact:
        return False
    if re.fullmatch(r"\d+(?:\.\d+)+", compact):
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?(?:万元|元|分|%)", compact):
        return True
    if re.fullmatch(r"[\d+\-*/=.()（）万元元分%]+", compact) and any(char.isdigit() for char in compact):
        return True
    return False


def _estimate_quality_score(text: str, report: OCRCleanupReport) -> float:
    if not text.strip():
        return 0.0
    lines = [line for line in text.splitlines() if line.strip()]
    question_hits = len(re.findall(r"(?m)^\s*\d{1,3}\s*[\.、．)]", text))
    option_hits = len(re.findall(r"(?m)^\s*[A-H][\.\、．)]", text))
    answer_hits = len(re.findall(r"(?:答案|参考答案|正确答案)\s*[:：]", text))
    analysis_hits = len(re.findall(r"(?:解析|答案解析|【解析】)\s*[:：]", text))
    signal = min(0.42, len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text)) / 1200)
    signal += min(0.18, question_hits * 0.05)
    signal += min(0.14, option_hits * 0.03)
    signal += min(0.12, answer_hits * 0.04)
    signal += min(0.12, analysis_hits * 0.04)
    penalty = min(0.2, report.removed_lines / max(1, report.input_lines) * 0.18)
    penalty += min(0.18, sum(1 for line in lines if len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", line)) <= 1) / max(1, len(lines)) * 0.18)
    score = 0.18 + signal - penalty
    return round(max(0.0, min(1.0, score)), 2)
