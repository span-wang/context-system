from __future__ import annotations

import json
import re

from llm.base import LLMProvider
from schemas.context import GenerationContext
from schemas.generation import GenerationResult
from schemas.review import ReviewMode


REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "pass_overall": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "suggestions": {"type": "array", "items": {"type": "string"}},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "issue": {"type": "string"},
                    "suggestion": {"type": "string"},
                    "original_text": {"type": "string"},
                    "replacement_text": {"type": "string"},
                },
                "required": ["issue"],
            },
        },
    },
    "required": ["pass_overall", "issues", "suggestions"],
}


async def llm_review(
    provider: LLMProvider,
    result: GenerationResult,
    context: GenerationContext,
    mode: ReviewMode,
    max_tokens: int,
) -> dict:
    try:
        payload = await provider.chat_json(
            [
                {"role": "system", "content": _system_prompt(mode)},
                {"role": "user", "content": _user_prompt(result, context, mode)},
            ],
            REVIEW_SCHEMA,
            max_tokens=max_tokens,
        )
    except json.JSONDecodeError:
        text = await provider.chat(
            [
                {"role": "system", "content": _system_prompt(mode)},
                {
                    "role": "user",
                    "content": _user_prompt(result, context, mode)
                    + "\n\n只返回 JSON，不要 Markdown 代码块。",
                },
            ],
            max_tokens=max_tokens,
        )
        payload = json.loads(_extract_json(text))
    return _normalize_payload(payload)


def _system_prompt(mode: ReviewMode) -> str:
    boundary = {
        "llm_only": "只使用你的通用专业知识和考试内容判断，不要把用户提供的资料当作审查依据。",
        "document_only": "只能根据审查依据文档判断。文档没有明确支持的内容，必须标记为未被依据文档支持；不得用外部知识补足。",
        "hybrid": "优先根据审查依据文档判断；文档不足时，可以结合你的通用专业知识指出风险，但要区分依据文档问题和模型判断问题。",
    }[mode]
    return (
        "你是严格的中文备考资料内容审查员。审查目标是发现文档中的事实错误、过时口径、数字/年份/条文风险、"
        "引用或依据不足，以及容易误导考生的表述。"
        f"{boundary}"
        "返回 JSON：pass_overall 为是否整体可发布；issues 为具体问题列表；suggestions 为修改建议列表。"
        "如能定位原文，请同时返回 items。items 每项包含 issue、suggestion、original_text、replacement_text。"
        "original_text 必须是待审查内容中可以直接搜索到的原文片段；replacement_text 是可直接替换进文中的修改稿。"
    )


def _user_prompt(result: GenerationResult, context: GenerationContext, mode: ReviewMode) -> str:
    parts = [
        f"审查模式：{mode}",
        f"学科：{context.subject}",
        f"类目：{context.category or '未填写'}",
        f"章节：{context.chapter or '未填写'}",
        "",
        "待审查内容：",
        result.raw_markdown[:120_000],
    ]
    if mode in {"document_only", "hybrid"}:
        parts.extend(["", "审查依据文档：", _format_sources(context)])
    return "\n".join(parts)


def _format_sources(context: GenerationContext) -> str:
    if not context.sources:
        return "未提供审查依据文档。"
    blocks: list[str] = []
    used_chars = 0
    max_chars = 120_000
    for index, source in enumerate(context.sources, 1):
        text = re.sub(r"\s+", " ", source.text or "").strip()
        if not text:
            continue
        remaining = max_chars - used_chars
        if remaining <= 0:
            blocks.append("审查依据文档过长，后续内容已截断。")
            break
        chunk = text[: min(len(text), remaining)]
        used_chars += len(chunk)
        blocks.append(f"[D{index}] {source.source_label}\n{chunk}")
    return "\n\n".join(blocks) if blocks else "审查依据文档没有可用正文。"


def _extract_json(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        return cleaned[start : end + 1]
    return cleaned


def _normalize_payload(payload: dict) -> dict:
    issues = payload.get("issues") or []
    suggestions = payload.get("suggestions") or []
    raw_items = payload.get("items") or []
    items = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        issue = str(item.get("issue") or "").strip()
        if not issue:
            continue
        items.append(
            {
                "issue": issue,
                "suggestion": str(item.get("suggestion") or "").strip() or None,
                "original_text": str(item.get("original_text") or "").strip() or None,
                "replacement_text": str(item.get("replacement_text") or "").strip() or None,
            }
        )
    return {
        "pass_overall": bool(payload.get("pass_overall")) if "pass_overall" in payload else not issues,
        "issues": [str(item) for item in issues if str(item).strip()],
        "suggestions": [str(item) for item in suggestions if str(item).strip()],
        "items": items,
    }
