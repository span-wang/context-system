from schemas.context import GenerationContext

from .base import TemplateGenerator


class CompareTableGenerator(TemplateGenerator):
    content_type = "compare_table"
    heading = "易错对比"

    def _sections(self, context: GenerationContext, outline: list[str], citations):
        rows = []
        paired = list(zip(outline[0::2], outline[1::2]))
        for index, pair in enumerate(paired[:6], 1):
            rows.append([f"易错点 {index}", pair[0], pair[1], "看关键词、适用条件和例外"])
        if not rows:
            rows = [["概念边界", "规则 A 待核验", "规则 B 待核验", "以官方资料为准"]]
        return [
            {
                "title": "对比表",
                "type": "table",
                "columns": ["对比项", "容易混淆 A", "容易混淆 B", "判断抓手"],
                "rows": rows,
                "citations": [c.model_dump() for c in citations],
            }
        ]

