from __future__ import annotations

import re
from dataclasses import dataclass

from app.models import Asset, Subject, SubjectCategory


@dataclass(frozen=True)
class TextbookChapterDraft:
    name: str
    points: list[str]


def build_textbook_outline(
    textbook: Asset,
    subject: Subject,
    category: SubjectCategory | None,
    max_chapters: int,
    points_per_chapter: int,
) -> tuple[str, list[TextbookChapterDraft]]:
    parsed_drafts = _outline_from_parsed_text(textbook.parsed_text or "", max_chapters, points_per_chapter)
    if parsed_drafts:
        return "parsed_text", parsed_drafts
    return "metadata", _outline_from_metadata(textbook, subject, category, max_chapters, points_per_chapter)


def auto_keywords(
    point_name: str,
    chapter_name: str,
    textbook: Asset,
    subject: Subject,
    category: SubjectCategory | None,
) -> list[str]:
    values = [point_name, _strip_chapter_prefix(chapter_name), subject.name]
    if category is not None:
        values.append(category.name)
    values.extend(_split_topics(point_name))
    version = _tag_value(textbook.tags_json, "version:")
    if version:
        values.append(version)
    return _dedupe(values)[:8]


def auto_point_description(textbook: Asset) -> str:
    return f"由《{textbook.source_title}》自动生成，状态为草稿，需人工核对名称、章节归属和关键词后启用。"


def normalized_entity_key(value: str) -> str:
    return re.sub(r"[\s/／\\\-_:：、，,。.;；（）()《》]+", "", value).lower()


_OUTLINE_TEMPLATES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("会计",),
        ("总论与会计基础", "存货与固定资产", "无形资产与投资性房地产", "金融资产和金融负债", "收入、费用和利润", "长期股权投资与合并报表", "所得税与会计调整", "财务报告"),
    ),
    (
        ("审计",),
        ("审计基础与职业规范", "审计计划与风险评估", "内部控制与控制测试", "审计证据与审计程序", "各类交易和账户审计", "审计报告与沟通", "职业道德与质量管理"),
    ),
    (
        ("税法", "税法一", "税法二", "税务"),
        ("税法总论与纳税管理", "增值税", "消费税", "企业所得税", "个人所得税", "其他税种", "税收征收管理"),
    ),
    (
        ("财管", "财务管理"),
        ("财务管理基础", "预算与成本管理", "筹资管理", "投资管理", "营运资金管理", "财务分析与评价"),
    ),
    (
        ("经济法", "法律"),
        ("法律基础", "公司法律制度", "证券法律制度", "合同法律制度", "物权与担保制度", "破产与票据法律制度"),
    ),
    (
        ("战略",),
        ("战略分析", "战略选择", "战略实施", "公司治理", "风险管理与内部控制"),
    ),
    (
        ("数学",),
        ("函数与导数", "数列", "三角函数", "解析几何", "立体几何", "概率与统计", "综合题型方法"),
    ),
    (
        ("英语",),
        ("词汇与语法", "阅读理解", "完形与语篇", "翻译", "写作", "真题题型训练"),
    ),
    (
        ("语文",),
        ("现代文阅读", "古诗文阅读", "语言文字运用", "写作", "文学文化常识", "综合题型训练"),
    ),
    (
        ("物理",),
        ("力学", "电磁学", "热学", "光学", "原子物理", "实验与综合应用"),
    ),
    (
        ("化学",),
        ("化学基本概念", "物质结构与性质", "化学反应原理", "有机化学", "化学实验", "综合推断"),
    ),
    (
        ("生物",),
        ("细胞与分子基础", "遗传与进化", "稳态与调节", "生态系统", "实验与探究", "综合应用"),
    ),
    (
        ("法规", "安全生产法律法规"),
        ("安全生产法律基础", "生产经营单位责任", "从业人员权利义务", "安全监管与行政执法", "事故报告与法律责任"),
    ),
    (
        ("管理", "安全生产管理"),
        ("安全管理基础", "风险分级管控", "隐患排查治理", "应急管理", "事故调查分析", "安全文化与标准化"),
    ),
    (
        ("安全工程师", "安全生产", "安全技术"),
        ("安全技术基础", "危险源辨识", "作业安全管理", "事故预防与控制", "应急处置", "案例综合分析"),
    ),
    (
        ("建筑", "建造师"),
        ("建筑工程技术", "项目施工管理", "工程法规与合同", "质量与安全控制", "进度与成本控制", "案例综合应用"),
    ),
)

_CHAPTER_PATTERNS = (
    re.compile(r"^(第[零〇一二三四五六七八九十百千万\d]+[章节篇编单元讲部分])[\s　、.．:：-]*(.+)?$"),
    re.compile(r"^((?:专题|模块)\s*[零〇一二三四五六七八九十百千万\d]+)[\s　、.．:：-]*(.+)?$"),
)
_SECTION_PATTERN = re.compile(r"^第[零〇一二三四五六七八九十百千万\d]+节[\s　、.．:：-]*(.+)$")
_NUMBERED_HEADING_PATTERN = re.compile(r"^(?:[（(]?[一二三四五六七八九十\d]{1,3}[）)、.．]|[0-9]{1,2}[.．、])\s*(.+)$")
_POINT_LABEL_PATTERN = re.compile(r"^(?:知识点|考点|要点)\s*[零〇一二三四五六七八九十\d]*[\s　、.．:：-]*(.+)$")
_NOISE_WORDS = ("目录", "本章小结", "复习思考题", "练习题", "学习目标", "考试大纲", "参考答案", "附录", "二维码")


def _outline_from_parsed_text(text: str, max_chapters: int, points_per_chapter: int) -> list[TextbookChapterDraft]:
    lines = _clean_lines(text)
    if not lines:
        return []

    chapter_indexes: list[tuple[int, str]] = []
    seen: set[str] = set()
    for index, line in enumerate(lines):
        chapter = _parse_chapter_heading(line)
        if chapter is None:
            continue
        key = normalized_entity_key(chapter)
        if key in seen:
            continue
        seen.add(key)
        chapter_indexes.append((index, chapter))
        if len(chapter_indexes) >= max_chapters:
            break

    drafts: list[TextbookChapterDraft] = []
    for position, (start_index, chapter_name) in enumerate(chapter_indexes):
        end_index = chapter_indexes[position + 1][0] if position + 1 < len(chapter_indexes) else len(lines)
        section_lines = lines[start_index + 1 : end_index]
        points = _extract_points(section_lines, chapter_name, points_per_chapter)
        drafts.append(TextbookChapterDraft(name=chapter_name, points=points))
    return drafts


def _outline_from_metadata(
    textbook: Asset,
    subject: Subject,
    category: SubjectCategory | None,
    max_chapters: int,
    points_per_chapter: int,
) -> list[TextbookChapterDraft]:
    book_subject = _title_subject(textbook.source_title)
    signal = " ".join(
        item
        for item in (
            category.name if category else "",
            book_subject,
            textbook.source_title,
            textbook.filename,
            subject.name,
            " ".join(textbook.tags_json or []),
        )
        if item
    )
    chapter_names = _template_chapters(category.name if category else "") or _template_chapters(book_subject) or _template_chapters(signal)
    if not chapter_names:
        base_name = category.name if category else book_subject or subject.name
        chapter_names = (
            f"{base_name}基础知识",
            f"{base_name}核心概念",
            f"{base_name}规则与方法",
            f"{base_name}综合应用",
            f"{base_name}真题与易错点",
        )

    drafts = []
    for chapter_name in _dedupe(chapter_names)[:max_chapters]:
        drafts.append(TextbookChapterDraft(name=chapter_name, points=_fallback_points(chapter_name, signal, points_per_chapter)))
    return drafts


def _clean_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text[:800_000].splitlines():
        line = _clean_heading(raw_line)
        if line:
            lines.append(line)
    return lines


def _clean_heading(value: str) -> str:
    text = re.sub(r"\s+", " ", value.strip())
    text = re.sub(r"[.·•…]{2,}\s*\d+\s*$", "", text).strip()
    return text.strip(" -—_")


def _parse_chapter_heading(line: str) -> str | None:
    if len(line) > 64 or _has_noise(line):
        return None
    for pattern in _CHAPTER_PATTERNS:
        match = pattern.match(line)
        if match:
            return _clean_heading(" ".join(part for part in match.groups() if part))
    return None


def _extract_points(lines: list[str], chapter_name: str, limit: int) -> list[str]:
    points: list[str] = []
    for line in lines:
        candidate = _parse_point_heading(line)
        if candidate is None:
            continue
        points.append(candidate)
        if len(_dedupe(points)) >= limit:
            break

    values = _dedupe(points)
    if len(values) < limit:
        values.extend(item for item in _fallback_points(chapter_name, chapter_name, limit) if item not in values)
    return values[:limit]


def _parse_point_heading(line: str) -> str | None:
    if len(line) > 56 or _has_noise(line) or _parse_chapter_heading(line):
        return None
    for pattern in (_POINT_LABEL_PATTERN, _SECTION_PATTERN, _NUMBERED_HEADING_PATTERN):
        match = pattern.match(line)
        if match:
            candidate = _clean_heading(match.group(1))
            return candidate if _looks_like_point(candidate) else None
    return None


def _looks_like_point(value: str) -> bool:
    if not 2 <= len(value) <= 40:
        return False
    if _has_noise(value):
        return False
    if re.fullmatch(r"[\d\s.．、]+", value):
        return False
    if value.endswith(("。", "；", ";")):
        return False
    return True


def _has_noise(value: str) -> bool:
    return any(word in value for word in _NOISE_WORDS)


def _template_chapters(signal: str) -> tuple[str, ...]:
    for keywords, chapters in _OUTLINE_TEMPLATES:
        if any(keyword in signal for keyword in keywords):
            return chapters
    return ()


def _fallback_points(chapter_name: str, signal: str, limit: int) -> list[str]:
    core = _strip_chapter_prefix(chapter_name)
    topics = [topic for topic in _split_topics(core) if topic != core]
    points: list[str] = []
    for topic in topics:
        points.append(f"{topic}核心考点")

    hints = _point_hints(core + signal)
    for hint in hints:
        points.append(f"{core}{hint}")
    return _dedupe(points)[:limit]


def _point_hints(signal: str) -> tuple[str, ...]:
    if any(keyword in signal for keyword in ("税", "纳税")):
        return ("征税范围", "计税依据", "应纳税额计算", "税收优惠与征管", "易错辨析")
    if any(keyword in signal for keyword in ("会计", "资产", "负债", "收入", "报表")):
        return ("确认条件", "初始计量", "后续计量", "列报与披露", "典型分录")
    if any(keyword in signal for keyword in ("审计", "证据", "控制")):
        return ("目标与程序", "风险识别", "证据获取", "底稿与结论", "易错辨析")
    if any(keyword in signal for keyword in ("财务", "财管", "成本", "预算")):
        return ("指标口径", "计算模型", "决策方法", "风险与评价", "综合题型")
    if any(keyword in signal for keyword in ("法", "合同", "公司", "证券")):
        return ("主体与权利义务", "成立与效力", "责任承担", "争议处理", "案例辨析")
    return ("基本概念", "核心规则", "方法步骤", "典型题型", "易错辨析")


def _strip_chapter_prefix(value: str) -> str:
    text = re.sub(r"^第[零〇一二三四五六七八九十百千万\d]+[章节篇编单元讲部分]\s*", "", value).strip()
    text = re.sub(r"^(?:专题|模块)\s*[零〇一二三四五六七八九十百千万\d]+\s*", "", text).strip()
    return text or value


def _split_topics(value: str) -> list[str]:
    return [
        item
        for item in (_clean_heading(part) for part in re.split(r"[、，,和与及/／]+", value))
        if 2 <= len(item) <= 18
    ]


def _title_subject(title: str) -> str:
    match = re.search(r"《([^》]+)》", title)
    if match:
        return _clean_heading(match.group(1))
    cleaned = re.sub(r"(教材|官方|考试|精讲|基础班|强化班|最新版|第.+版|\d{4})", "", title)
    parts = _split_topics(cleaned)
    return parts[0] if parts else _clean_heading(cleaned)


def _tag_value(tags: list[str] | None, prefix: str) -> str | None:
    for tag in tags or []:
        if isinstance(tag, str) and tag.startswith(prefix):
            value = tag.removeprefix(prefix).strip()
            return value or None
    return None


def _dedupe(values: list[str] | tuple[str, ...]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_heading(str(value))
        key = normalized_entity_key(text)
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result
