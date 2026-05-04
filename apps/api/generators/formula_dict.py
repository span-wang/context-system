import re

from schemas.context import GenerationContext

from .base import TemplateGenerator


class FormulaDictGenerator(TemplateGenerator):
    content_type = "formula_dict"
    heading = "公式/分录大全"

    def _sections(self, context: GenerationContext, outline: list[str], citations):
        formulas = []
        pattern = re.compile(r"([\u4e00-\u9fa5A-Za-z0-9（）()]+)\s*[=:＝]\s*([^。；;\n]{2,80})")
        for source in context.sources:
            formulas.extend(pattern.findall(source.text))
        items = []
        for name, expr in formulas[:12]:
            items.append(f"{name.strip()} = {expr.strip()}；适用条件请回看原文。")
        if not items:
            items = [f"{item}；请补充适用条件、例题和来源页码。" for item in outline[:8]]
        return [{"title": "公式与分录", "items": items, "citations": [c.model_dump() for c in citations]}]

