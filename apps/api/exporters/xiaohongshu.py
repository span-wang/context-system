from __future__ import annotations

import re

from schemas.context import GenerationContext
from schemas.generation import XiaohongshuPublishPackage


UNVERIFIED_WARNING = "> 未核验：本次未提供权威资料，请对照最新官方教材/规范核对后使用。"


def build_publish_package_from_markdown(
    *,
    title: str,
    markdown: str,
    context: GenerationContext,
    sections: list[dict] | None = None,
    unverified: bool = False,
) -> XiaohongshuPublishPackage:
    body = _normalize_body(markdown, title, unverified)
    key_points = _key_points_from_sections(sections or []) or _key_points_from_markdown(body)
    title_options = _title_options(title, context, key_points)
    tags = _tags(context)
    return XiaohongshuPublishPackage(
        title_options=title_options,
        body=body,
        cover_text=_cover_text(title, key_points),
        carousel_pages=[],
        tags=tags,
        comment_guides=[],
    )


def render_publish_package(package: XiaohongshuPublishPackage, fallback_title: str | None = None) -> str:
    title_options = _ensure_count(package.title_options, 5, fallback_title or "小红书笔记标题")
    lines = [
        "# 小红书发布包",
        "",
        "## 笔记标题 5 个备选",
    ]
    lines.extend(f"{index}. {item}" for index, item in enumerate(title_options[:5], 1))
    lines.extend(
        [
            "",
            "## 正文",
            "",
            (package.body or "").strip(),
            "",
            "## 封面文案",
            "",
            (package.cover_text or "").strip(),
            "",
        ]
    )
    lines.extend(["", "## 标签建议", ""])
    lines.append(" ".join(_format_tag(tag) for tag in package.tags))
    return "\n".join(lines).strip() + "\n"


def package_from_json_payload(payload: dict, fallback_body: str = "") -> XiaohongshuPublishPackage:
    return XiaohongshuPublishPackage(
        title_options=_string_list(payload.get("title_options") or payload.get("笔记标题") or payload.get("笔记标题备选")),
        body=_string_value(payload.get("body") or payload.get("正文") or fallback_body),
        cover_text=_string_value(payload.get("cover_text") or payload.get("封面文案")),
        carousel_pages=[],
        tags=_string_list(payload.get("tags") or payload.get("标签建议") or payload.get("标签")),
        comment_guides=[],
    )


def normalize_publish_package(
    package: XiaohongshuPublishPackage,
    *,
    title: str,
    markdown: str,
    context: GenerationContext,
    sections: list[dict] | None = None,
    unverified: bool = False,
) -> XiaohongshuPublishPackage:
    fallback = build_publish_package_from_markdown(
        title=title,
        markdown=markdown,
        context=context,
        sections=sections,
        unverified=unverified,
    )
    return XiaohongshuPublishPackage(
        title_options=_ensure_count(package.title_options, 5, title, fallback.title_options)[:5],
        body=_normalize_body(package.body or fallback.body, title, unverified),
        cover_text=(package.cover_text or fallback.cover_text).strip(),
        carousel_pages=[],
        tags=package.tags or fallback.tags,
        comment_guides=[],
    )


def _normalize_body(markdown: str, title: str, unverified: bool) -> str:
    body = _strip_non_body_sections(markdown.strip())
    if not body.startswith("#"):
        body = f"# {title}\n\n{body}"
    if unverified and UNVERIFIED_WARNING not in body:
        lines = body.splitlines()
        insert_at = 2 if lines and lines[0].startswith("# ") else 0
        lines[insert_at:insert_at] = ["", UNVERIFIED_WARNING, ""]
        body = "\n".join(lines)
    return body.strip()


def _strip_non_body_sections(text: str) -> str:
    if not text:
        return text
    non_body_section_pattern = re.compile(
        r"^\s{0,3}#{1,6}\s*(?:"
        r"笔记标题(?:\s*5\s*个)?备选|"
        r"标题(?:备选|建议)?|"
        r"封面文案|"
        r"轮播图逐页文案|"
        r"轮播图|"
        r"标签建议|"
        r"评论区引导|"
        r"评论引导"
        r")\s*$",
        flags=re.MULTILINE,
    )
    body_section_pattern = re.compile(r"^\s{0,3}#{1,6}\s*(?:正文|发布正文)\s*$", flags=re.MULTILINE)
    body_match = body_section_pattern.search(text)
    if body_match:
        body_start = body_match.end()
        next_non_body = non_body_section_pattern.search(text, body_start)
        body_end = next_non_body.start() if next_non_body else len(text)
        return text[body_start:body_end].strip()
    match = non_body_section_pattern.search(text)
    return text[: match.start()].strip() if match else text


def _title_options(title: str, context: GenerationContext, key_points: list[str]) -> list[str]:
    topic = _topic_label(context) or title
    chapter = context.chapter or context.category or context.subject
    first_point = _short_text(key_points[0], 22) if key_points else "高频考点"
    return _dedupe(
        [
            f"{chapter}别再死记硬背：一篇理顺",
            f"{topic}考前速记版，收藏就能背",
            f"{first_point}，很多人第一遍都会错",
            f"{context.subject}备考人必看：{chapter}核心笔记",
            f"{topic}一图流复盘，考前快速过一遍",
        ]
    )[:5]


def _cover_text(title: str, key_points: list[str]) -> str:
    if key_points:
        return f"{_short_text(_strip_markdown(key_points[0]), 18)}\n考前别漏"
    return f"{_short_text(title, 18)}\n考前速记"


def _tags(context: GenerationContext) -> list[str]:
    base = [
        context.subject,
        context.category,
        context.chapter,
        "备考",
        "考前冲刺",
        "小红书学习",
    ]
    return _dedupe([_clean_tag(item) for item in base if item])[:8]


def _key_points_from_sections(sections: list[dict]) -> list[str]:
    points: list[str] = []
    for section in sections:
        title = str(section.get("title") or "").strip()
        rows = section.get("items") or section.get("rows") or []
        if title:
            points.append(title)
        for row in rows:
            if isinstance(row, list):
                text = " / ".join(str(cell) for cell in row if str(cell).strip())
            else:
                text = str(row)
            if text.strip():
                points.append(text.strip())
    return _dedupe(points)[:8]


def _key_points_from_markdown(markdown: str) -> list[str]:
    points = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("> 未核验"):
            continue
        stripped = re.sub(r"^#{1,6}\s*", "", stripped)
        stripped = stripped.strip(" -*|")
        if len(stripped) >= 8:
            points.append(stripped)
    return _dedupe(points)[:8]


def _ensure_count(items: list[str], count: int, seed: str, fallback: list[str] | None = None) -> list[str]:
    merged = _dedupe([*items, *(fallback or [])])
    while len(merged) < count:
        merged.append(f"{seed}备考重点 {len(merged) + 1}")
    return merged


def _string_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        lines = [line.strip(" -0123456789.、\t") for line in value.splitlines()]
        return [line for line in lines if line]
    return [str(value).strip()] if str(value).strip() else []


def _string_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def _topic_label(context: GenerationContext) -> str:
    return " · ".join(item for item in [context.subject, context.category, context.chapter] if item)


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = re.sub(r"\s+", " ", str(item or "")).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _strip_markdown(text: str) -> str:
    return re.sub(r"[*_`>#\[\]()-]+", "", text).strip()


def _short_text(text: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    return cleaned if len(cleaned) <= limit else f"{cleaned[:limit]}..."


def _clean_tag(tag: str) -> str:
    return re.sub(r"[#\s]+", "", tag).strip()


def _format_tag(tag: str) -> str:
    cleaned = _clean_tag(tag)
    return f"#{cleaned}" if cleaned else ""
