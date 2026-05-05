from __future__ import annotations

import re
from abc import ABC, abstractmethod

from exporters.xiaohongshu import build_publish_package_from_markdown
from schemas.context import GenerationContext
from schemas.generation import Citation, Claim, GenerationResult


CONTENT_LABELS = {
    "mnemonic": "口诀",
    "tri_color": "三色笔记",
    "summary_pages": "考前资料",
    "formula_dict": "公式/分录大全",
    "compare_table": "易错对比",
    "exam_review": "真题串讲",
}


class BaseGenerator(ABC):
    content_type: str

    @abstractmethod
    async def generate(self, context: GenerationContext) -> GenerationResult:
        raise NotImplementedError


class TemplateGenerator(BaseGenerator):
    heading: str = "备考资料"

    async def generate(self, context: GenerationContext) -> GenerationResult:
        outline = self._outline(context)
        citations = self._citations(context)
        claims = [Claim(text=item, citations=citations[:1]) for item in outline[:8]]
        title = self._title(context)
        sections = self._sections(context, outline, citations)
        markdown = self._markdown(title, sections, citations, unverified=not context.sources)
        publish_package = build_publish_package_from_markdown(
            title=title,
            markdown=markdown,
            context=context,
            sections=sections,
            unverified=not context.sources,
        )
        return GenerationResult(
            content_type=context.content_type,
            title=title,
            sections=sections,
            claims=claims,
            raw_markdown=markdown,
            publish_package=publish_package,
            unverified=not context.sources,
        )

    def _title(self, context: GenerationContext) -> str:
        parts = [context.subject]
        if context.category:
            parts.append(context.category)
        if context.chapter:
            parts.append(context.chapter)
        parts.append(CONTENT_LABELS.get(context.content_type, self.heading))
        return " · ".join(parts)

    def _sections(
        self,
        context: GenerationContext,
        outline: list[str],
        citations: list[Citation],
    ) -> list[dict]:
        return [{"title": self.heading, "items": outline, "citations": [c.model_dump() for c in citations]}]

    def _markdown(self, title: str, sections: list[dict], citations: list[Citation], unverified: bool) -> str:
        lines = [f"# {title}", ""]
        if unverified:
            lines.extend(["> 未核验：本次未提供权威资料，请对照最新官方教材/规范核对后使用。", ""])
        for section in sections:
            lines.extend([f"## {section.get('title', '内容')}", ""])
            rows = section.get("items") or section.get("rows") or []
            if section.get("type") == "table":
                columns = section.get("columns") or ["对比项", "A", "B"]
                lines.append("| " + " | ".join(columns) + " |")
                lines.append("| " + " | ".join(["---"] * len(columns)) + " |")
                for row in rows:
                    lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
            else:
                for item in rows:
                    lines.append(f"- {item}")
            lines.append("")
        if citations:
            lines.extend(["## 引用来源", ""])
            for index, citation in enumerate(citations, 1):
                lines.append(f"{index}. {citation.source_label}：{citation.snippet}")
        return "\n".join(lines).strip() + "\n"

    def _outline(self, context: GenerationContext) -> list[str]:
        source_text = "\n".join(source.text for source in context.sources)
        if context.user_notes:
            source_text = f"{source_text}\n{context.user_notes}"
        candidates = _sentences(source_text)
        if not candidates:
            base = "、".join(filter(None, [context.subject, context.category, context.chapter])) or context.subject
            candidates = [
                f"围绕{base}梳理高频考点。",
                "优先核对最新教材、规范、法规和真题口径。",
                "输出仅作为初稿，正式使用前需要人工复核。",
            ]
        return candidates[:10]

    def _citations(self, context: GenerationContext) -> list[Citation]:
        citations: list[Citation] = []
        for source in context.sources[:6]:
            snippet = _sentences(source.text)[:1]
            citations.append(
                Citation(
                    source_label=source.source_label,
                    chunk_id=source.chunk_id,
                    file_id=source.file_id,
                    page=source.page,
                    snippet=snippet[0] if snippet else source.text[:160],
                )
            )
        return citations


def _sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return []
    pieces = re.split(r"(?<=[。！？!?；;])\s+|[\r\n]+", cleaned)
    fallback = re.split(r"[。！？!?；;]", cleaned)
    raw = pieces if len(pieces) > 1 else fallback
    sentences: list[str] = []
    for item in raw:
        item = item.strip(" -\t")
        if len(item) < 8:
            continue
        sentences.append(item[:220])
    return sentences
