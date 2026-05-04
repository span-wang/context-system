from __future__ import annotations

import re

from llm.base import LLMProvider
from schemas.context import GenerationContext
from schemas.generation import Citation, Claim, GenerationResult
from settings import LLMEndpointConfig

from .base import CONTENT_LABELS, BaseGenerator, TemplateGenerator, _sentences


CONTENT_GUIDANCE = {
    "mnemonic": "输出便于背诵的口诀、拆解和使用场景。",
    "tri_color": "按红色必背、蓝色理解、黑色拓展组织内容。",
    "summary_pages": "输出考前速览资料，按页感分块，突出高频结论。",
    "formula_dict": "整理公式、会计分录、适用条件和易错点。",
    "compare_table": "用表格对比易混概念、适用场景、判断口诀和错误提醒。",
    "exam_review": "围绕真题串讲知识点、题眼和解题步骤。",
}


class LLMContentGenerator(BaseGenerator):
    content_type = "llm"

    def __init__(self, provider: LLMProvider, endpoint: LLMEndpointConfig) -> None:
        self.provider = provider
        self.endpoint = endpoint
        self.template = TemplateGenerator()

    async def generate(self, context: GenerationContext) -> GenerationResult:
        title = self.template._title(context)
        citations = self.template._citations(context)
        markdown = await self.provider.chat(
            [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": _user_prompt(context, title)},
            ],
            max_tokens=_max_output_tokens(context, self.endpoint.max_tokens),
        )
        markdown = _normalize_markdown(markdown, title, unverified=not context.sources)
        claims = _claims_from_markdown(markdown, citations)
        return GenerationResult(
            content_type=context.content_type,
            title=title,
            sections=[
                {
                    "title": "LLM 生成结果",
                    "items": [claim.text for claim in claims[:12]],
                    "citations": [c.model_dump() for c in citations],
                }
            ],
            claims=claims,
            raw_markdown=markdown,
            unverified=not context.sources,
        )


def _system_prompt() -> str:
    return (
        "你是严谨的中文备考资料编辑，擅长把考试资料改写成小红书风格但不牺牲准确性。"
        "只输出 Markdown 正文，不要包裹代码块，不要解释自己是模型。"
        "如果没有提供权威资料，必须在开头保留未核验提示，并避免编造具体条文、年份、税率或官方口径。"
        "如果提供了素材，优先依据素材，不确定的内容写成待核对。"
    )


def _user_prompt(context: GenerationContext, title: str) -> str:
    pages = context.options.get("pages", 8)
    parts = [
        f"标题：{title}",
        f"学科：{context.subject}",
        f"类目：{context.category or '未填写'}",
        f"章节：{context.chapter or '未填写'}",
        f"内容类型：{CONTENT_LABELS.get(context.content_type, context.content_type)}",
        f"目标页数：{pages}",
        f"补充说明：{context.user_notes or '无'}",
        "",
        "输出要求：",
        f"- {CONTENT_GUIDANCE.get(context.content_type, '输出结构化备考资料。')}",
        "- 标题层级清晰，适合直接复制到 Markdown 编辑器。",
        "- 多用短段落、列表、表格，避免空泛套话。",
        "- 重要结论后补一句易错提醒或使用条件。",
    ]
    if context.sources:
        parts.extend(
            [
                "- 引用素材观点时在句末标注来源编号，例如 [S1]。",
                "",
                "素材：",
                _format_sources(context),
            ]
        )
    else:
        parts.extend(
            [
                "- 本次没有权威素材，开头必须包含：> 未核验：本次未提供权威资料，请对照最新官方教材/规范核对后使用。",
                "- 不要写引用来源章节。",
            ]
        )
    return "\n".join(parts)


def _format_sources(context: GenerationContext) -> str:
    blocks: list[str] = []
    used_chars = 0
    max_chars = 120_000
    for index, source in enumerate(context.sources, 1):
        text = re.sub(r"\s+", " ", source.text or "").strip()
        if not text:
            continue
        remaining = max_chars - used_chars
        if remaining <= 0:
            blocks.append("素材过长，后续内容已截断。")
            break
        chunk = text[: min(len(text), remaining)]
        used_chars += len(chunk)
        blocks.append(f"[S{index}] {source.source_label}\n{chunk}")
    return "\n\n".join(blocks) if blocks else "无可用素材正文。"


def _normalize_markdown(markdown: str, title: str, unverified: bool) -> str:
    text = markdown.strip()
    text = re.sub(r"^```(?:markdown|md)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    if not text.startswith("#"):
        text = f"# {title}\n\n{text}"
    warning = "> 未核验：本次未提供权威资料，请对照最新官方教材/规范核对后使用。"
    if unverified and warning not in text:
        lines = text.splitlines()
        insert_at = 2 if lines and lines[0].startswith("# ") else 0
        lines[insert_at:insert_at] = ["", warning, ""]
        text = "\n".join(lines)
    return text.strip() + "\n"


def _claims_from_markdown(markdown: str, citations: list[Citation]) -> list[Claim]:
    cleaned = re.sub(r"```.*?```", "", markdown, flags=re.DOTALL)
    lines = []
    for line in cleaned.splitlines():
        stripped = line.strip(" \t-*#>|")
        if len(stripped) >= 8 and not stripped.startswith("未核验"):
            lines.append(stripped[:220])
    candidates = lines[:12] or _sentences(cleaned)[:12]
    attached = citations[:1]
    return [Claim(text=item, citations=attached) for item in candidates]


def _max_output_tokens(context: GenerationContext, configured_limit: int) -> int:
    try:
        pages = int(context.options.get("pages") or 8)
    except (TypeError, ValueError):
        pages = 8
    task_limit = max(1200, min(32_000, pages * 1800))
    return max(1, min(configured_limit, task_limit))
