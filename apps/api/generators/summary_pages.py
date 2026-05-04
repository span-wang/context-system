from schemas.context import GenerationContext

from .base import TemplateGenerator


class SummaryPagesGenerator(TemplateGenerator):
    content_type = "summary_pages"
    heading = "考前压缩资料"

    def _sections(self, context: GenerationContext, outline: list[str], citations):
        page_count = int(context.options.get("pages", 10) or 10)
        page_count = max(1, min(page_count, 30))
        sections = []
        for index in range(page_count):
            start = index * 3
            items = outline[start : start + 3] or outline[:3] or ["本页内容待补充。"]
            sections.append(
                {
                    "title": f"第 {index + 1} 页",
                    "items": items,
                    "citations": [c.model_dump() for c in citations],
                }
            )
        return sections

