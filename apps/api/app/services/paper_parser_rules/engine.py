from __future__ import annotations

import re
from html import unescape
from dataclasses import dataclass, field

from library.parser import ParsedDocument, ParsedPage


QUESTION_START_PATTERN = re.compile(
    r"^\s*(?:#+\s*)?(?:第\s*)?(?P<no>[0-9]{1,3}|[一二三四五六七八九十百]{1,6})\s*(?:题|[\.、．)])\s*"
)
CHAPTER_HEADER_PATTERN = re.compile(r"^\s*(?:#+\s*)?第\s*[一二三四五六七八九十百0-9]+\s*章\s*$")
SECTION_HEADER_PATTERN = re.compile(
    r"^\s*(?:#+\s*)?"
    r"(?:(?:第\s*[一二三四五六七八九十百0-9]+\s*部分)|(?:[一二三四五六七八九十百0-9]+\s*[\.、．]))?\s*"
    r"(?P<title>单项选择题|多项选择题|不定项选择题|判断题|填空题|简答题|计算题|案例分析题|综合题|材料分析题)"
    r"(?:\s*[\(（:：].*)?\s*$"
)
OPTION_LINE_PATTERN = re.compile(r"^\s*[A-H][\.\、．)]\s*")
OPTION_PATTERN = re.compile(r"(?m)^\s*([A-H])[\.\、．)]\s*(.+?)(?=(?:\n\s*[A-H][\.\、．)]\s*)|\Z)", re.S)
INLINE_OPTION_PATTERN = re.compile(r"([A-H])[\.\、．)]\s*")
ANSWER_LINE_PATTERN = re.compile(r"^\s*(?:#+\s*)?(?:答案|参考答案|正确答案)\s*[:：]")
ANALYSIS_LINE_PATTERN = re.compile(r"^\s*(?:#+\s*)?(?:解析|答案解析|【解析】)\s*(?:[:：]|\s*$)")
ANSWER_PATTERN = re.compile(
    r"(?ms)^\s*(?:#+\s*)?(?:答案|参考答案|正确答案)\s*[:：]\s*(.+?)(?=^\s*(?:#+\s*)?(?:解析|答案解析|【解析】)\s*(?:[:：]|\n)|\Z)"
)
ANALYSIS_PATTERN = re.compile(r"(?ms)^\s*(?:#+\s*)?(?:解析|答案解析|【解析】)\s*(?:[:：]\s*|\n+)(.+)$")
ANSWER_ANALYSIS_HEADER_PATTERN = re.compile(r"(?m)^\s*(?:#+\s*)?答案与解析\s*$")
SHARED_CONTEXT_CUE_PATTERN = re.compile(
    r"(?:根据下列资料|根据上述资料|阅读下列材料|回答下列|下列小题|资料一|资料二|资料三)"
)
BLANK_LINE_PATTERN = re.compile(r"[（(]\s*[）)]|[_＿—–-]{2,}")
TRAILING_OPTION_HINT_PATTERN = re.compile(r"(?<![A-Za-z0-9])([A-H])\s*$")
TRAILING_OCR_GARBAGE_PATTERN = re.compile(r"[Oo0Ｏ○·•]\s*$")
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
SUBQUESTION_PATTERN = re.compile(r"(?m)^\s*[(（]([1-9][0-9]{0,2}|[一二三四五六七八九十]+)[)）]\s*")
SUBQUESTION_LABEL_PATTERN = re.compile(r"(?m)(?:^|\s)第\s*([1-9][0-9]{0,2}|[一二三四五六七八九十]+)\s*小题")
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
class RuleLine:
    text: str
    page_number: int
    x1: float = 0.0
    y1: float = 0.0
    x2: float = 0.0
    y2: float = 0.0
    column_idx: int = 0
    is_noise: bool = False

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)


@dataclass(slots=True)
class RuleBlock:
    raw_text: str
    question_no_override: str | None = None
    stem_prefix: str | None = None


@dataclass(slots=True)
class RuleSection:
    title: str
    section_type: str
    sort_order: int
    blocks: list[RuleBlock] = field(default_factory=list)


@dataclass(slots=True)
class RuleQuestion:
    question_no: str
    question_type: str
    stem_text: str
    options: list[str]
    answer_text: str | None
    analysis_text: str | None
    difficulty_level: int
    quality_score: float
    subquestion_count: int
    source_section_name: str
    quality_issues: list[str] = field(default_factory=list)


def parse_sections_with_rules(document: ParsedDocument) -> list[RuleSection]:
    lines = _build_rule_lines(document)
    lines = _filter_noise_lines(lines)
    if not lines:
        return [RuleSection(title="自动切题", section_type="mixed", sort_order=1, blocks=[])]

    section_spans = _split_sections(lines)
    sections: list[RuleSection] = []
    for sort_order, span in enumerate(section_spans, start=1):
        blocks = _split_questions(span.lines)
        if blocks:
            sections.append(
                RuleSection(
                    title=span.title,
                    section_type=span.section_type,
                    sort_order=sort_order,
                    blocks=blocks,
                )
            )

    if sections:
        return sections
    return [
        RuleSection(
            title="自动切题",
            section_type="mixed",
            sort_order=1,
            blocks=_split_questions(lines),
        )
    ]


def parse_sections_from_text(text: str) -> list[RuleSection]:
    normalized = _normalize_source_text(text)
    document = ParsedDocument(
        text=normalized,
        markdown=normalized,
        provider="rules_text_fallback",
        pages=[ParsedPage(page_number=1, text=normalized, markdown=normalized)],
    )
    return parse_sections_with_rules(document)


def adapt_llm_sections(
    raw_sections: list[dict[str, object]] | None,
    *,
    fallback_text: str = "",
) -> list[RuleSection]:
    sections: list[RuleSection] = []
    for index, item in enumerate(raw_sections or [], start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip() or "自动切题"
        section_type = str(item.get("section_type") or "mixed").strip()
        if section_type not in SECTION_TYPE_MAP.values() and section_type != "mixed":
            section_type = "mixed"
        raw_blocks = item.get("blocks")
        if not isinstance(raw_blocks, list):
            continue
        blocks: list[RuleBlock] = []
        for block_item in raw_blocks:
            if not isinstance(block_item, dict):
                continue
            raw_text = str(block_item.get("raw_text") or "").strip()
            if not raw_text:
                continue
            blocks.append(
                RuleBlock(
                    raw_text=raw_text,
                    question_no_override=str(block_item.get("question_no_override") or "").strip() or None,
                    stem_prefix=str(block_item.get("stem_prefix") or "").strip() or None,
                )
            )
        if blocks:
            sections.append(
                RuleSection(
                    title=title,
                    section_type=section_type,
                    sort_order=index,
                    blocks=blocks,
                )
            )

    if sections:
        return sections
    if fallback_text.strip():
        return parse_sections_from_text(fallback_text)
    return []


def parse_questions_from_sections(sections: list[RuleSection]) -> list[tuple[RuleSection, RuleQuestion]]:
    parsed: list[tuple[RuleSection, RuleQuestion]] = []
    for section in sections:
        for block in section.blocks:
            parsed.append((section, _parse_rule_block(block, section)))
    return parsed


def parse_question_block(block: RuleBlock, section: RuleSection) -> RuleQuestion:
    return _parse_rule_block(block, section)


@dataclass(slots=True)
class _SectionSpan:
    title: str
    section_type: str
    lines: list[RuleLine]


def _build_rule_lines(document: ParsedDocument) -> list[RuleLine]:
    all_lines: list[RuleLine] = []
    for page in document.pages:
        page_lines = _build_page_lines(page)
        all_lines.extend(page_lines)
    return all_lines


def _build_page_lines(page: ParsedPage) -> list[RuleLine]:
    raw_lines: list[RuleLine] = []
    if page.blocks:
        blocks = _sorted_page_blocks(page.blocks)
        for block in blocks:
            text = (block.latex or block.text or "").strip()
            if not text:
                continue
            x1, y1, x2, y2 = _bbox4(block.bbox)
            raw_lines.append(
                RuleLine(
                    text=text,
                    page_number=page.page_number,
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2,
                )
            )
    elif page.text:
        for index, text in enumerate(page.text.splitlines(), start=1):
            normalized = text.strip()
            if not normalized:
                continue
            raw_lines.append(
                RuleLine(
                    text=normalized,
                    page_number=page.page_number,
                    y1=float(index),
                    y2=float(index),
                )
            )

    if not raw_lines:
        return []

    threshold = _detect_two_column_threshold(raw_lines, page.width)
    if threshold is not None:
        for line in raw_lines:
            center = (line.x1 + line.x2) / 2.0
            line.column_idx = 0 if center <= threshold else 1
        raw_lines.sort(key=lambda item: (item.column_idx, item.y1, item.x1, item.text))
    else:
        raw_lines.sort(key=lambda item: (item.y1, item.x1, item.text))

    return _merge_neighbor_lines(raw_lines)


def _sorted_page_blocks(blocks: list[object]) -> list[object]:
    if any(len(getattr(block, "bbox", None) or []) == 4 for block in blocks):
        return sorted(blocks, key=_page_block_sort_key)
    return list(blocks)


def _page_block_sort_key(block: object) -> tuple[float, float, str]:
    bbox = getattr(block, "bbox", None) or []
    if len(bbox) == 4:
        return (float(bbox[1]), float(bbox[0]), str(getattr(block, "block_id", "")))
    return (1e9, 1e9, str(getattr(block, "block_id", "")))


def _bbox4(bbox: list[float] | None) -> tuple[float, float, float, float]:
    if bbox and len(bbox) == 4:
        return float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
    return 0.0, 0.0, 0.0, 0.0


def _detect_two_column_threshold(lines: list[RuleLine], page_width: float) -> float | None:
    if page_width <= 0 or len(lines) < 8:
        return None
    centers = sorted((line.x1 + line.x2) / 2.0 for line in lines if line.width > 0)
    if len(centers) < 8:
        return None
    mid = len(centers) // 2
    left = centers[:mid]
    right = centers[mid:]
    if not left or not right:
        return None
    gap = min(right) - max(left)
    if gap < page_width * 0.08:
        return None

    largest_gap = -1.0
    threshold = centers[len(centers) // 2]
    for left, right in zip(centers, centers[1:]):
        gap = right - left
        if gap > largest_gap:
            largest_gap = gap
            threshold = (left + right) / 2.0
    left_lines = [line for line in lines if line.width > 0 and ((line.x1 + line.x2) / 2.0) <= threshold]
    right_lines = [line for line in lines if line.width > 0 and ((line.x1 + line.x2) / 2.0) > threshold]
    if len(left_lines) < 3 or len(right_lines) < 3:
        return None

    left_x1 = min(line.x1 for line in left_lines)
    left_x2 = max(line.x2 for line in left_lines)
    right_x1 = min(line.x1 for line in right_lines)
    right_x2 = max(line.x2 for line in right_lines)
    overlap = max(0.0, min(left_x2, right_x2) - max(left_x1, right_x1))
    narrower_width = max(1.0, min(left_x2 - left_x1, right_x2 - right_x1))
    if overlap / narrower_width >= 0.35:
        return None
    return threshold


def _merge_neighbor_lines(lines: list[RuleLine]) -> list[RuleLine]:
    merged: list[RuleLine] = []
    for line in lines:
        normalized = _normalize_line_text(line.text)
        if not normalized:
            continue
        line.text = normalized
        if not merged:
            merged.append(line)
            continue
        previous = merged[-1]
        if _should_merge_lines(previous, line):
            previous.text = f"{previous.text} {line.text}".strip()
            previous.x1 = min(previous.x1, line.x1)
            previous.y1 = min(previous.y1, line.y1)
            previous.x2 = max(previous.x2, line.x2)
            previous.y2 = max(previous.y2, line.y2)
            continue
        merged.append(line)
    return merged


def _should_merge_lines(previous: RuleLine, current: RuleLine) -> bool:
    if previous.page_number != current.page_number:
        return False
    if previous.column_idx != current.column_idx:
        return False
    if _is_section_header_line(previous.text) or _is_section_header_line(current.text):
        return False
    if _is_question_start_line(current.text):
        return False
    if _looks_like_single_prompt_question_line(current.text):
        return False
    if OPTION_LINE_PATTERN.match(previous.text) or OPTION_LINE_PATTERN.match(current.text):
        return False
    if _looks_like_accounting_entry_line(previous.text) or _looks_like_accounting_entry_line(current.text):
        return False
    if ANSWER_LINE_PATTERN.match(current.text) or ANALYSIS_LINE_PATTERN.match(current.text):
        return False
    if ANSWER_LINE_PATTERN.match(previous.text) or ANALYSIS_LINE_PATTERN.match(previous.text):
        return False
    if previous.y2 and current.y1 and current.y1 - previous.y2 > 24:
        return False
    if previous.x1 and current.x1 and abs(current.x1 - previous.x1) > 48:
        return False
    return len(previous.text) <= 24 or previous.text.endswith(("：", ":", "（", "(", "、"))


# P0 hotfix final override.
# Keep this at the end of the file so the parser uses the relaxed start score.

def _question_start_score(lines: list[RuleLine], index: int) -> int:
    line = lines[index].text.strip()
    score = 0
    if _is_question_start_line(line):
        score += 50
    if line.startswith(("O ", "O\t", "0 ", "○ ", "● ")):
        normalized = re.sub(r"^[Oo0Ｏ○●·•\s]+", "", line)
        if _is_question_start_line(normalized):
            score += 50
    if BLANK_LINE_PATTERN.search(line):
        score += 10
    if ANSWER_LINE_PATTERN.match(line) or ANALYSIS_LINE_PATTERN.match(line):
        score -= 40
    if OPTION_LINE_PATTERN.match(line):
        score -= 35
    option_count = _count_next_option_lines(lines, index + 1, max_scan=6)
    if option_count >= 2:
        score += 20
    elif option_count == 1:
        score += 10
    inline_option_count = len(_extract_inline_options(line)[1])
    if inline_option_count >= 2:
        score += 20
    if _looks_like_shared_context(line) and index + 1 < len(lines) and _is_question_start_line(lines[index + 1].text):
        score -= 25
    return score


def _normalize_line_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _normalize_source_text(text: str) -> str:
    normalized = unescape(text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n"))
    normalized = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", normalized)
    normalized = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", normalized)
    normalized = re.sub(r"(?i)</?(?:html|body|div|span|p|section|article|tbody|thead|tfoot|table|tr|td|th|br)[^>]*>", "\n", normalized)
    normalized = re.sub(r"(?is)<[^>]+>", " ", normalized)
    normalized = re.sub(
        r"(?<!\n)(\s*(?:单项选择题|多项选择题|不定项选择题|判断题|填空题|简答题|计算题|案例分析题|综合题|材料分析题)\s*\d{1,3}\s*[-－—–])",
        r"\n\1",
        normalized,
    )
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n[ \t]+", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _filter_noise_lines(lines: list[RuleLine]) -> list[RuleLine]:
    if not lines:
        return []
    repeated = _detect_repeated_noise(lines)
    kept: list[RuleLine] = []
    for line in lines:
        normalized = _noise_key(line.text)
        if normalized in repeated:
            continue
        if _looks_like_noise_line(line.text):
            continue
        kept.append(line)
    return kept


def _detect_repeated_noise(lines: list[RuleLine]) -> set[str]:
    page_hits: dict[str, set[int]] = {}
    for line in lines:
        compact = re.sub(r"\s+", "", line.text.strip())
        if not compact or compact.isdigit():
            continue
        normalized = _noise_key(line.text)
        if not normalized:
            continue
        page_hits.setdefault(normalized, set()).add(line.page_number)
    return {
        text
        for text, pages in page_hits.items()
        if len(pages) >= 2 and len(text) <= 80 and not _is_high_signal_line(text)
    }


def _noise_key(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip())
    normalized = re.sub(r"\d+", "#", normalized)
    return normalized


def _looks_like_noise_line(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return True
    if _is_high_signal_line(normalized):
        return False
    if re.fullmatch(r"第?\s*\d+\s*页", normalized):
        return True
    if re.fullmatch(r"\d", normalized):
        return True
    if re.fullmatch(r"[-_·•\s]+", normalized):
        return True
    if ("http://" in normalized or "https://" in normalized or "www." in normalized) and len(normalized) <= 80:
        return True
    if "微信公众号" in normalized or "扫码" in normalized or "内部资料" in normalized:
        return True
    return False


def _is_high_signal_line(text: str) -> bool:
    return bool(
        _is_question_start_line(text)
        or _is_chapter_header_line(text)
        or _is_section_header_line(text)
        or OPTION_LINE_PATTERN.match(text)
        or ANSWER_LINE_PATTERN.match(text)
        or ANALYSIS_LINE_PATTERN.match(text)
        or BLANK_LINE_PATTERN.search(text)
    )


def _split_sections(lines: list[RuleLine]) -> list[_SectionSpan]:
    headers: list[tuple[int, str, str]] = []
    for index, line in enumerate(lines):
        header = _parse_section_header(line.text)
        if header is None:
            continue
        headers.append((index, header[0], header[1]))

    if not headers:
        return [_SectionSpan(title="自动切题", section_type="mixed", lines=lines)]

    spans: list[_SectionSpan] = []
    for header_index, (start, title, section_type) in enumerate(headers):
        end = headers[header_index + 1][0] if header_index + 1 < len(headers) else len(lines)
        section_lines = [line for line in lines[start + 1 : end] if line.text.strip()]
        if not section_lines:
            continue
        spans.append(_SectionSpan(title=title, section_type=section_type, lines=section_lines))

    return spans or [_SectionSpan(title="自动切题", section_type="mixed", lines=lines)]


def _parse_section_header(text: str) -> tuple[str, str] | None:
    match = SECTION_HEADER_PATTERN.match(text.strip())
    if not match:
        return None
    title = match.group("title").strip()
    return title, SECTION_TYPE_MAP.get(title, "mixed")


def _is_chapter_header_line(text: str) -> bool:
    return CHAPTER_HEADER_PATTERN.match(text.strip()) is not None


def _is_section_header_line(text: str) -> bool:
    return _parse_section_header(text) is not None


def _split_questions(lines: list[RuleLine]) -> list[RuleBlock]:
    if not lines:
        return []

    starts = [index for index, line in enumerate(lines) if _question_start_score(lines, index) >= 45]
    if not starts:
        prompt_starts = [index for index, line in enumerate(lines) if _looks_like_prompt_question_line(lines, index)]
        if prompt_starts:
            return _split_prompt_questions(lines, prompt_starts)
        raw_text = "\n".join(line.text for line in lines if line.text.strip()).strip()
        return [RuleBlock(raw_text=raw_text)] if raw_text else []

    blocks: list[RuleBlock] = []
    leading_lines = lines[: starts[0]]
    shared_leading_text = "\n".join(line.text for line in leading_lines if line.text.strip()).strip()

    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        block_lines = lines[start:end]
        raw_text = "\n".join(line.text for line in block_lines if line.text.strip()).strip()
        if not raw_text:
            continue
        blocks.append(RuleBlock(raw_text=raw_text))

    if not blocks:
        return []

    if shared_leading_text:
        if _looks_like_shared_context(shared_leading_text):
            for block in blocks:
                block.stem_prefix = shared_leading_text
        else:
            blocks[0].raw_text = f"{shared_leading_text}\n{blocks[0].raw_text}".strip()

    return _attach_inline_shared_context(blocks)


def _question_start_score(lines: list[RuleLine], index: int) -> int:
    line = lines[index].text.strip()
    score = 0
    if _is_question_start_line(line):
        score += 40
    if BLANK_LINE_PATTERN.search(line):
        score += 10
    if ANSWER_LINE_PATTERN.match(line) or ANALYSIS_LINE_PATTERN.match(line):
        score -= 40
    if OPTION_LINE_PATTERN.match(line):
        score -= 35
    option_count = _count_next_option_lines(lines, index + 1, max_scan=6)
    if option_count >= 2:
        score += 20
    elif option_count == 1:
        score += 10
    inline_option_count = len(_extract_inline_options(line)[1])
    if inline_option_count >= 2:
        score += 20
    if _looks_like_shared_context(line) and index + 1 < len(lines) and _is_question_start_line(lines[index + 1].text):
        score -= 25
    return score


def _is_question_start_line(text: str) -> bool:
    return QUESTION_START_PATTERN.match(text.strip()) is not None


def _count_next_option_lines(lines: list[RuleLine], start_index: int, max_scan: int) -> int:
    count = 0
    scanned = 0
    for offset in range(start_index, len(lines)):
        candidate = lines[offset].text.strip()
        if not candidate:
            continue
        scanned += 1
        if OPTION_LINE_PATTERN.match(candidate):
            count += 1
        if _is_question_start_line(candidate) or ANSWER_LINE_PATTERN.match(candidate) or ANALYSIS_LINE_PATTERN.match(candidate):
            break
        if scanned >= max_scan:
            break
    return count


def _looks_like_shared_context(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    if SHARED_CONTEXT_CUE_PATTERN.search(normalized):
        return True
    if re.search(r"(?m)(?:^|[\n。；;])\s*要求(?:[:：]|\s)", normalized):
        return True
    return "资料" in normalized and "题" in normalized and len(normalized) >= 12


def _attach_inline_shared_context(blocks: list[RuleBlock]) -> list[RuleBlock]:
    result: list[RuleBlock] = []
    pending_context: str | None = None
    for block in blocks:
        raw_text = block.raw_text.strip()
        start_match = QUESTION_START_PATTERN.match(raw_text)
        content = raw_text[start_match.end() :].strip() if start_match else raw_text
        if (
            _looks_like_shared_context(content)
            and len(_extract_question_option_lines(content)) < 2
            and len(_extract_inline_options(content)[1]) < 2
        ):
            pending_context = content
            continue
        if pending_context and block.stem_prefix is None:
            block.stem_prefix = pending_context
        result.append(block)
    return result or blocks


def _extract_question_option_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if OPTION_LINE_PATTERN.match(line.strip())]


def _looks_like_accounting_entry_line(text: str) -> bool:
    normalized = text.strip()
    return normalized.startswith(("借：", "贷：", "借:", "贷:"))


def _looks_like_single_prompt_question_line(text: str) -> bool:
    line = text.strip()
    if len(line) < 8:
        return False
    if OPTION_LINE_PATTERN.match(line):
        return False
    if ANSWER_LINE_PATTERN.match(line) or ANALYSIS_LINE_PATTERN.match(line):
        return False
    return "根据" in line or "下列" in line or "表述" in line or "说法" in line or "处理" in line


def _looks_like_prompt_question_line(lines: list[RuleLine], index: int) -> bool:
    line = lines[index].text.strip()
    if not _looks_like_single_prompt_question_line(line):
        return False
    option_count = _count_next_option_lines(lines, index + 1, max_scan=8)
    if option_count >= 2:
        return True
    return BLANK_LINE_PATTERN.search(line) is not None


def _split_prompt_questions(lines: list[RuleLine], starts: list[int]) -> list[RuleBlock]:
    blocks: list[RuleBlock] = []
    leading_lines = lines[: starts[0]]
    shared_leading_text = "\n".join(line.text for line in leading_lines if line.text.strip()).strip()
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        cursor = end
        while cursor < len(lines):
            candidate = lines[cursor].text.strip()
            if not candidate:
                cursor += 1
                continue
            if _looks_like_single_prompt_question_line(candidate) or _is_question_start_line(candidate):
                break
            end = cursor + 1
            cursor += 1
        block_lines = lines[start:end]
        raw_text = "\n".join(line.text for line in block_lines if line.text.strip()).strip()
        if not raw_text:
            continue
        blocks.append(
            RuleBlock(
                raw_text=raw_text,
                question_no_override=str(index + 1),
            )
        )
    if shared_leading_text:
        if _looks_like_shared_context(shared_leading_text):
            for block in blocks:
                block.stem_prefix = shared_leading_text
        elif blocks:
            blocks[0].raw_text = f"{shared_leading_text}\n{blocks[0].raw_text}".strip()
    return _collapse_leading_context_only_blocks(blocks)


def _collapse_leading_context_only_blocks(blocks: list[RuleBlock]) -> list[RuleBlock]:
    if len(blocks) < 2:
        return blocks
    first = blocks[0]
    if _extract_question_option_lines(first.raw_text):
        return blocks
    if ANSWER_LINE_PATTERN.search(first.raw_text) or ANALYSIS_LINE_PATTERN.search(first.raw_text):
        return blocks
    if not _looks_like_shared_context(first.raw_text):
        return blocks

    shared_context = first.raw_text.strip()
    merged: list[RuleBlock] = []
    for index, block in enumerate(blocks[1:], start=1):
        if not block.stem_prefix:
            block.stem_prefix = shared_context
        block.question_no_override = str(index)
        merged.append(block)
    return merged or blocks


def _parse_rule_block(block: RuleBlock, section: RuleSection) -> RuleQuestion:
    raw_text = block.raw_text.strip()
    number_match = QUESTION_START_PATTERN.match(raw_text)
    question_no = block.question_no_override or (number_match.group("no") if number_match else str(section.sort_order))
    content = raw_text[number_match.end() :].strip() if number_match else raw_text
    content = ANSWER_ANALYSIS_HEADER_PATTERN.sub("", content).strip()

    content_without_solution, answer_text, analysis_text = _extract_solution_parts(content)
    stem, options = _extract_stem_and_options(content_without_solution)
    stem = re.sub(r"\n{3,}", "\n\n", stem)
    if block.stem_prefix:
        stem = f"{block.stem_prefix}\n\n{stem}".strip()
    subquestion_count = _count_subquestion_markers(content_without_solution)
    contextual_subquestion_count = subquestion_count
    if block.stem_prefix:
        contextual_subquestion_count = max(contextual_subquestion_count, _count_subquestion_markers(block.stem_prefix))
    question_type = _detect_question_type(
        section.section_type,
        options,
        answer_text,
        content_without_solution,
        contextual_subquestion_count,
    )
    quality_score = _estimate_quality_score(
        stem,
        options,
        answer_text,
        analysis_text,
        contextual_subquestion_count,
        section.section_type,
    )
    quality_issues = _collect_quality_issues(
        question_type=question_type,
        stem=stem,
        options=options,
        answer_text=answer_text,
        analysis_text=analysis_text,
        quality_score=quality_score,
    )
    difficulty = _estimate_difficulty(question_type, contextual_subquestion_count)
    return RuleQuestion(
        question_no=str(question_no),
        question_type=question_type,
        stem_text=stem or block.stem_prefix or content[:500] or f"第 {question_no} 题",
        options=options,
        answer_text=answer_text,
        analysis_text=analysis_text,
        difficulty_level=difficulty,
        quality_score=quality_score,
        subquestion_count=contextual_subquestion_count,
        source_section_name=section.title,
        quality_issues=quality_issues,
    )


def _extract_solution_parts(content: str) -> tuple[str, str | None, str | None]:
    answer_match = _find_earliest_match(ANSWER_HEADER_INLINE_PATTERNS, content)
    analysis_match = _find_earliest_match(ANALYSIS_HEADER_INLINE_PATTERNS, content)

    if answer_match is None and analysis_match is None:
        return content.strip(), _extract_pattern(ANSWER_PATTERN, content), _extract_pattern(ANALYSIS_PATTERN, content)

    if answer_match and (analysis_match is None or answer_match.start() <= analysis_match.start()):
        answer_end = answer_match.end()
        answer_stop = analysis_match.start() if analysis_match and analysis_match.start() > answer_end else len(content)
        content_without_solution = content[: answer_match.start()].strip()
        answer_text = _clean_solution_text(content[answer_end:answer_stop])
        analysis_text = _clean_solution_text(content[analysis_match.end() :]) if analysis_match else None
        return content_without_solution, answer_text, analysis_text

    analysis_end = analysis_match.end() if analysis_match else 0
    analysis_stop = answer_match.start() if answer_match and answer_match.start() > analysis_end else len(content)
    content_without_solution = content[: analysis_match.start()].strip() if analysis_match else content.strip()
    answer_text = _clean_solution_text(content[answer_match.end() :]) if answer_match else None
    analysis_text = _clean_solution_text(content[analysis_end:analysis_stop]) if analysis_match else None
    return content_without_solution, answer_text, analysis_text


def _extract_stem_and_options(content: str) -> tuple[str, list[str]]:
    line_options = [f"{match.group(1).upper()}. {_normalize_option_text(match.group(2))}" for match in OPTION_PATTERN.finditer(content)]
    expanded_line_options: list[str] = []
    for option in line_options:
        expanded_line_options.extend(_split_dense_option_line(option))
    line_options = expanded_line_options or line_options
    line_stem = _normalize_question_stem(OPTION_PATTERN.sub("", content), line_options)
    inline_stem, inline_options = _extract_inline_options(content)
    inline_stem = _normalize_question_stem(inline_stem, inline_options)

    if len(inline_options) > len(line_options):
        return inline_stem, inline_options
    if len(line_options) >= 2:
        return line_stem, line_options
    if len(inline_options) >= 2:
        return inline_stem, inline_options
    if line_options:
        return line_stem, line_options
    if inline_options:
        return inline_stem, inline_options
    return content.strip(), []


def _extract_inline_options(content: str) -> tuple[str, list[str]]:
    matches = list(INLINE_OPTION_PATTERN.finditer(content))
    if len(matches) < 2:
        return content.strip(), []

    best_run: list[re.Match[str]] = []
    current_run: list[re.Match[str]] = []
    previous_label = ""
    for match in matches:
        label = match.group(1).upper()
        if current_run and label <= previous_label:
            if len(current_run) > len(best_run):
                best_run = current_run
            current_run = [match]
        else:
            current_run.append(match)
        previous_label = label
    if len(current_run) > len(best_run):
        best_run = current_run
    if len(best_run) < 2:
        return content.strip(), []

    if not _looks_like_inline_option_run(content, best_run):
        return content.strip(), []

    stem = content[: best_run[0].start()].strip()
    options: list[str] = []
    for index, match in enumerate(best_run):
        end = best_run[index + 1].start() if index + 1 < len(best_run) else len(content)
        option_text = _normalize_option_text(content[match.end() : end])
        if option_text:
            options.append(f"{match.group(1).upper()}. {option_text}")
    if len(options) < 2:
        return content.strip(), []
    return stem, options


def _split_dense_option_line(line: str) -> list[str]:
    matches = list(INLINE_OPTION_PATTERN.finditer(line))
    if len(matches) < 2:
        return [line]
    pieces: list[str] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
        option_text = _normalize_option_text(line[match.end() : end])
        if option_text:
            pieces.append(f"{match.group(1).upper()}. {option_text}")
    return pieces or [line]


def _looks_like_inline_option_run(content: str, matches: list[re.Match[str]]) -> bool:
    first = matches[0]
    first_label = first.group(1).upper()
    stem = content[: first.start()].strip()
    if first_label != "A":
        return False
    if not stem:
        return False
    if "（" not in stem and "(" not in stem and "下列" not in stem and "的是" not in stem and "正确" not in stem:
        return False

    labels = [match.group(1).upper() for match in matches]
    unique_labels = []
    for label in labels:
        if label not in unique_labels:
            unique_labels.append(label)
    if unique_labels[:2] != ["A", "B"]:
        return False
    return True


def _normalize_question_stem(stem: str, options: list[str]) -> str:
    text = stem.strip()
    if not text:
        return text
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\s{2,}", " ", text)
    if len(options) >= 2:
        text = TRAILING_OPTION_HINT_PATTERN.sub("", text).strip()
    text = _strip_trailing_ocr_garbage(text, options)
    return text


def _normalize_option_text(value: str) -> str:
    text = value.strip()
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ \t]*\n[ \t]*", " ", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def _strip_trailing_ocr_garbage(text: str, options: list[str]) -> str:
    if not text:
        return text
    if "（）" not in text and "()" not in text and "（)" not in text and "(）" not in text:
        return text
    if not options:
        return text
    cleaned = text
    while True:
        updated = TRAILING_OCR_GARBAGE_PATTERN.sub("", cleaned).strip()
        if updated == cleaned:
            return cleaned
        cleaned = updated


def _clean_solution_text(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    text = _truncate_at_structural_boundary(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text or None


def _find_earliest_match(patterns: tuple[re.Pattern[str], ...], text: str) -> re.Match[str] | None:
    earliest: re.Match[str] | None = None
    for pattern in patterns:
        match = pattern.search(text)
        if match is None:
            continue
        if earliest is None or match.start() < earliest.start():
            earliest = match
    return earliest


def _truncate_at_structural_boundary(text: str) -> str:
    boundary_matches = []
    for pattern in (
        CHAPTER_HEADER_PATTERN,
        SECTION_HEADER_PATTERN,
    ):
        boundary_matches.extend(pattern.finditer(text))
    earliest_start = min((match.start() for match in boundary_matches), default=None)
    if earliest_start is None:
        return text.strip()
    return text[:earliest_start].strip()


def _count_subquestion_markers(text: str) -> int:
    if not text:
        return 0
    return len(SUBQUESTION_PATTERN.findall(text)) + len(SUBQUESTION_LABEL_PATTERN.findall(text))


def _extract_pattern(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip() or None


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
    if re.search(r"[_＿]{2,}", content_without_answer) or BLANK_LINE_PATTERN.search(content_without_answer):
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


def _estimate_difficulty(question_type: str, subquestion_count: int) -> int:
    if question_type in {"single_choice", "judge"}:
        return 2
    if question_type in {"multiple_choice", "fill_blank", "short_answer"}:
        return 3
    if question_type in {"calculation", "case_analysis", "material_analysis", "composite"}:
        return 4 if subquestion_count >= 2 else 3
    return 3


# P0 hotfix: append-only compatibility patch.
# Do not insert this patch into the middle of the file.

_P0_SECTION_TYPE_ALIASES = {
    "选择题": "single_choice",
    "客观题": "single_choice",
    "非选择题": "mixed",
    "主观题": "mixed",
}
_P0_SECTION_HEADER_FALLBACK_PATTERN = re.compile(
    r"^\s*(?:#+\s*)?"
    r"(?:(?:第\s*[一二三四五六七八九十百0-9]+\s*部分)|(?:[一二三四五六七八九十百0-9]+\s*[\.、．。]))?\s*"
    r"(?P<title>选择题|客观题|非选择题|主观题|单项选择题|多项选择题|不定项选择题|判断题|填空题|简答题|计算题|案例分析题|综合题|材料分析题)"
    r"(?:\s*[\(（:：].*)?\s*$"
)
_P0_MATERIAL_GROUP_HEADER_PATTERN = re.compile(
    r"^\s*(?:#+\s*)?"
    r"(?P<title>单项选择题|多项选择题|不定项选择题|判断题|填空题|简答题|计算题|案例分析题|综合题|材料分析题)"
    r"\s*\d{1,3}\s*[-－—–]\s*.+$"
)
_P0_INLINE_QUESTION_START_PATTERN = re.compile(
    r"(?<!^)(?<!\d)(?P<no>[0-9]{1,3}|[一二三四五六七八九十百]{1,6})[\.、．)](?=\S)"
)
_P0_INLINE_RANGE_PREFIX_PATTERN = re.compile(
    r"(?:完成|回答|解答)\s*\d+\s*[~～\-—–到至]\s*\d+\s*题[。．.]?$"
)
_P0_INLINE_OCR_GARBAGE_PATTERN = re.compile(r"^[Oo0Ｏ○●·•\s]+$")

_P0_ORIGINAL_SPLIT_QUESTIONS = _split_questions


def _build_page_lines(page: ParsedPage) -> list[RuleLine]:
    raw_lines: list[RuleLine] = []
    used_bbox = False
    if page.blocks:
        blocks = _sorted_page_blocks(page.blocks)
        for index, block in enumerate(blocks, start=1):
            text = (block.latex or block.text or "").strip()
            if not text:
                continue
            bbox = getattr(block, "bbox", None) or []
            if len(bbox) == 4:
                x1, y1, x2, y2 = _bbox4(bbox)
                used_bbox = True
            else:
                x1 = 0.0
                x2 = 0.0
                y1 = float(index)
                y2 = float(index)
            raw_lines.append(
                RuleLine(
                    text=text,
                    page_number=page.page_number,
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2,
                )
            )
    elif page.text:
        for index, text in enumerate(page.text.splitlines(), start=1):
            normalized = text.strip()
            if not normalized:
                continue
            raw_lines.append(
                RuleLine(
                    text=normalized,
                    page_number=page.page_number,
                    y1=float(index),
                    y2=float(index),
                )
            )

    if not raw_lines:
        return []

    if used_bbox:
        threshold = _detect_two_column_threshold(raw_lines, page.width)
        if threshold is not None:
            for line in raw_lines:
                center = (line.x1 + line.x2) / 2.0
                line.column_idx = 0 if center <= threshold else 1
            raw_lines.sort(key=lambda item: (item.column_idx, item.y1, item.x1, item.text))
        else:
            raw_lines.sort(key=lambda item: (item.y1, item.x1, item.text))

    return _merge_neighbor_lines(raw_lines)


def _parse_section_header(text: str) -> tuple[str, str] | None:
    normalized = text.strip()
    match = SECTION_HEADER_PATTERN.match(normalized)
    if match:
        title = match.group("title").strip()
        return title, SECTION_TYPE_MAP.get(title, "mixed")

    material_match = _P0_MATERIAL_GROUP_HEADER_PATTERN.match(normalized)
    if material_match is not None:
        title = material_match.group("title").strip()
        return title, SECTION_TYPE_MAP.get(title, "mixed")

    fallback = _P0_SECTION_HEADER_FALLBACK_PATTERN.match(normalized)
    if fallback is None:
        return None
    title = fallback.group("title").strip()
    section_type = _P0_SECTION_TYPE_ALIASES.get(title, SECTION_TYPE_MAP.get(title, "mixed"))
    return title, section_type


def _is_question_start_line(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    if _parse_section_header(normalized) is not None:
        return False
    return QUESTION_START_PATTERN.match(normalized) is not None


def _split_sections(lines: list[RuleLine]) -> list[_SectionSpan]:
    headers: list[tuple[int, str, str]] = []
    for index, line in enumerate(lines):
        header = _parse_section_header(line.text)
        if header is None:
            continue
        headers.append((index, header[0], header[1]))

    if not headers:
        return [_SectionSpan(title="自动切题", section_type="mixed", lines=lines)]

    spans: list[_SectionSpan] = []
    first_header_index = headers[0][0]
    leading_lines = [line for line in lines[:first_header_index] if line.text.strip()]
    if leading_lines and _p0_lines_contain_question_signal(leading_lines):
        section_type = _p0_infer_leading_section_type(leading_lines)
        spans.append(
            _SectionSpan(
                title=_p0_default_section_title(section_type),
                section_type=section_type,
                lines=leading_lines,
            )
        )

    for header_index, (start, title, section_type) in enumerate(headers):
        end = headers[header_index + 1][0] if header_index + 1 < len(headers) else len(lines)
        section_lines = [line for line in lines[start + 1 : end] if line.text.strip()]
        if not section_lines:
            continue
        spans.append(_SectionSpan(title=title, section_type=section_type, lines=section_lines))

    return spans or [_SectionSpan(title="自动切题", section_type="mixed", lines=lines)]


def _split_questions(lines: list[RuleLine]) -> list[RuleBlock]:
    return _P0_ORIGINAL_SPLIT_QUESTIONS(_p0_expand_embedded_question_lines(lines))


def _p0_lines_contain_question_signal(lines: list[RuleLine]) -> bool:
    return any(
        _is_question_start_line(line.text)
        or _p0_has_inline_question_boundary(line.text)
        or _looks_like_prompt_question_line(lines, index)
        for index, line in enumerate(lines)
    )


def _p0_infer_leading_section_type(lines: list[RuleLine]) -> str:
    option_line_count = sum(1 for line in lines if OPTION_LINE_PATTERN.match(line.text.strip()))
    prompt_count = sum(1 for index, _ in enumerate(lines) if _looks_like_prompt_question_line(lines, index))
    if prompt_count >= 1 and option_line_count >= 2:
        return "multiple_choice"
    if option_line_count >= 2:
        return "single_choice"
    return "mixed"


def _p0_default_section_title(section_type: str) -> str:
    if section_type == "single_choice":
        return "选择题"
    if section_type == "multiple_choice":
        return "多项选择题"
    return "自动切题"


def _p0_expand_embedded_question_lines(lines: list[RuleLine]) -> list[RuleLine]:
    expanded: list[RuleLine] = []
    for line in lines:
        parts = _p0_split_inline_question_text(line.text)
        if len(parts) <= 1:
            expanded.append(line)
            continue
        for part in parts:
            expanded.append(
                RuleLine(
                    text=part,
                    page_number=line.page_number,
                    x1=line.x1,
                    y1=line.y1,
                    x2=line.x2,
                    y2=line.y2,
                    column_idx=line.column_idx,
                    is_noise=line.is_noise,
                )
            )
    return expanded


def _p0_split_inline_question_text(text: str) -> list[str]:
    current = text.strip()
    if not current:
        return []
    parts: list[str] = []
    while current:
        match = _p0_find_inline_question_boundary(current)
        if match is None:
            parts.append(current.strip())
            break
        prefix = current[: match.start()].strip()
        suffix = current[match.start() :].strip()
        if prefix and not _P0_INLINE_OCR_GARBAGE_PATTERN.fullmatch(prefix):
            parts.append(prefix)
        current = suffix
    return [part for part in parts if part]


def _p0_find_inline_question_boundary(text: str) -> re.Match[str] | None:
    for match in _P0_INLINE_QUESTION_START_PATTERN.finditer(text):
        prefix = text[: match.start()].strip()
        suffix = text[match.start() :].strip()
        if _p0_is_inline_question_boundary(prefix, suffix):
            return match
    return None


def _p0_has_inline_question_boundary(text: str) -> bool:
    return _p0_find_inline_question_boundary(text.strip()) is not None


def _p0_is_inline_question_boundary(prefix: str, suffix: str) -> bool:
    if not prefix or not suffix:
        return False
    start_match = QUESTION_START_PATTERN.match(suffix)
    if start_match is None:
        return False
    body = suffix[start_match.end() :].strip()
    if len(body) < 6:
        return False
    if _P0_INLINE_OCR_GARBAGE_PATTERN.fullmatch(prefix):
        return True
    if OPTION_LINE_PATTERN.match(prefix):
        return True
    if _P0_INLINE_RANGE_PREFIX_PATTERN.search(prefix):
        return True
    if prefix.endswith(("。", "！", "？", "；", ";", "）", ")", "]", "】")):
        return True
    if "完成" in prefix and "题" in prefix:
        return True
    return False


def _split_questions(lines: list[RuleLine]) -> list[RuleBlock]:
    expanded = _p0_expand_embedded_question_lines(lines)
    prompt_starts = _collect_prompt_starts(expanded)
    prefer_prompt = any(_looks_like_material_group_header(line.text) for line in expanded)
    starts = [index for index, line in enumerate(expanded) if _question_start_score(expanded, index) >= 45]
    if prefer_prompt and prompt_starts:
        starts = [index for index in starts if index in prompt_starts]
    if not starts:
        if prompt_starts:
            return _split_prompt_questions(expanded, prompt_starts)
        raw_text = "\n".join(line.text for line in expanded if line.text.strip()).strip()
        return [RuleBlock(raw_text=raw_text)] if raw_text else []

    blocks: list[RuleBlock] = []
    leading_lines = expanded[: starts[0]]
    shared_leading_text = "\n".join(line.text for line in leading_lines if line.text.strip()).strip()

    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(expanded)
        block_lines = expanded[start:end]
        raw_text = "\n".join(line.text for line in block_lines if line.text.strip()).strip()
        if not raw_text:
            continue
        blocks.append(RuleBlock(raw_text=raw_text))

    if not blocks:
        return []

    if shared_leading_text:
        if _looks_like_shared_context(shared_leading_text):
            for block in blocks:
                block.stem_prefix = shared_leading_text
        else:
            blocks[0].raw_text = f"{shared_leading_text}\n{blocks[0].raw_text}".strip()

    if prompt_starts and _looks_like_invalid_number_sequence(blocks):
        return _split_prompt_questions(expanded, prompt_starts)

    return _attach_inline_shared_context(blocks)


def _question_start_score(lines: list[RuleLine], index: int) -> int:
    line = lines[index].text.strip()
    score = 0
    if _is_effective_question_start_line(line):
        score += 40
    if line.startswith(("O ", "O\t", "0 ", "○ ", "● ")):
        normalized = re.sub(r"^[Oo0Ｏ○●·•\s]+", "", line)
        if _is_effective_question_start_line(normalized):
            score += 50
    if BLANK_LINE_PATTERN.search(line):
        score += 10
    if ANSWER_LINE_PATTERN.match(line) or ANALYSIS_LINE_PATTERN.match(line):
        score -= 40
    if OPTION_LINE_PATTERN.match(line):
        score -= 35
    option_count = _count_next_option_lines(lines, index + 1, max_scan=6)
    if option_count >= 2:
        score += 20
    elif option_count == 1:
        score += 10
    inline_option_count = len(_extract_inline_options(line)[1])
    if inline_option_count >= 2:
        score += 20
    if _looks_like_numeric_fragment(line):
        score -= 50
    if _looks_like_shared_context(line) and index + 1 < len(lines) and _is_effective_question_start_line(lines[index + 1].text):
        score -= 25
    return score


_P0_INLINE_QUESTION_START_PATTERN = re.compile(
    r"(?<!^)(?<!\d)(?P<no>[0-9]{1,3}|[一二三四五六七八九十百]{1,6})[\.、．)]\s*(?=\S)"
)


def _looks_like_numeric_fragment(text: str) -> bool:
    compact = re.sub(r"\s+", "", text.strip())
    if not compact:
        return False
    if re.fullmatch(r"\d+(?:\.\d+)+", compact):
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?(?:万元|元|分|%)", compact):
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?(?:年|月|日)", compact):
        return True
    if re.fullmatch(r"[\d+\-*/=.()（）万元元分%]+", compact) and any(char.isdigit() for char in compact):
        return True
    return False


def _looks_like_material_group_header(text: str) -> bool:
    normalized = text.strip()
    return _P0_MATERIAL_GROUP_HEADER_PATTERN.match(normalized) is not None


def _looks_like_suspicious_numeric_question_start(line: str) -> bool:
    normalized = line.strip()
    match = QUESTION_START_PATTERN.match(normalized)
    if match is None:
        return False
    body = normalized[match.end() :].strip()
    if not body:
        return False
    if _looks_like_numeric_fragment(body):
        return True
    if re.match(r"^(?:\d{4}年|\d{1,2}月\d{1,2}日)", body):
        return True
    return False


def _is_effective_question_start_line(text: str) -> bool:
    return _is_question_start_line(text) and not _looks_like_suspicious_numeric_question_start(text)


def _looks_like_invalid_number_sequence(blocks: list[RuleBlock]) -> bool:
    suspicious = 0
    numeric = 0
    for block in blocks[:8]:
        raw_text = block.raw_text.strip()
        if not raw_text:
            continue
        start_match = QUESTION_START_PATTERN.match(raw_text)
        if start_match is None:
            continue
        numeric += 1
        body = raw_text[start_match.end() :].strip()
        if _looks_like_numeric_fragment(body):
            suspicious += 1
    return numeric >= 2 and suspicious >= 2


def _collect_prompt_starts(lines: list[RuleLine]) -> list[int]:
    starts = [index for index, line in enumerate(lines) if _looks_like_prompt_question_line(lines, index)]
    filtered: list[int] = []
    for index in starts:
        previous = lines[index - 1].text.strip() if index > 0 else ""
        current = lines[index].text.strip()
        if filtered and index - filtered[-1] <= 1 and _looks_like_shared_context(previous):
            continue
        if current.startswith("要求") and index + 1 < len(lines) and _looks_like_prompt_question_line(lines, index + 1):
            continue
        filtered.append(index)
    return filtered


def _p0_is_inline_question_boundary(prefix: str, suffix: str) -> bool:
    if not prefix or not suffix:
        return False
    start_match = QUESTION_START_PATTERN.match(suffix)
    if start_match is None:
        return False
    body = suffix[start_match.end() :].strip()
    if len(body) < 2:
        return False
    if _looks_like_numeric_fragment(body):
        return False
    if OPTION_LINE_PATTERN.match(prefix) and re.fullmatch(r"\s*[A-H][\.\、．)]\s*", prefix):
        return False
    if _P0_INLINE_OCR_GARBAGE_PATTERN.fullmatch(prefix):
        return True
    if re.search(r"[Oo0Ｏ○●·•]\s*$", prefix):
        return True
    if OPTION_LINE_PATTERN.match(prefix):
        return True
    if _P0_INLINE_RANGE_PREFIX_PATTERN.search(prefix):
        return True
    if prefix.endswith(("。", "！", "？", "；", ";", "）", ")", "]", "】")):
        return True
    if "完成" in prefix and "题" in prefix:
        return True
    return False


def _should_merge_lines(previous: RuleLine, current: RuleLine) -> bool:
    if previous.page_number != current.page_number:
        return False
    if previous.column_idx != current.column_idx:
        return False
    if _is_section_header_line(previous.text) or _is_section_header_line(current.text):
        return False
    if _is_question_start_line(current.text):
        return False
    normalized_current = re.sub(r"^[Oo0Ｏ○●·•\s]+", "", current.text.strip())
    if normalized_current != current.text.strip() and _is_question_start_line(normalized_current):
        return False
    if _p0_has_inline_question_boundary(current.text):
        return False
    if _looks_like_single_prompt_question_line(current.text):
        return False
    if OPTION_LINE_PATTERN.match(previous.text) or OPTION_LINE_PATTERN.match(current.text):
        return False
    if _looks_like_accounting_entry_line(previous.text) or _looks_like_accounting_entry_line(current.text):
        return False
    if ANSWER_LINE_PATTERN.match(current.text) or ANALYSIS_LINE_PATTERN.match(current.text):
        return False
    if ANSWER_LINE_PATTERN.match(previous.text) or ANALYSIS_LINE_PATTERN.match(previous.text):
        return False
    if previous.y2 and current.y1 and current.y1 - previous.y2 > 24:
        return False
    if previous.x1 and current.x1 and abs(current.x1 - previous.x1) > 48:
        return False
    return len(previous.text) <= 24 or previous.text.endswith(("：", ":", "（", "(", "、"))
