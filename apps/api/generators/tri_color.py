from schemas.context import GenerationContext

from .base import TemplateGenerator


class TriColorGenerator(TemplateGenerator):
    content_type = "tri_color"
    heading = "三色笔记"

    def _sections(self, context: GenerationContext, outline: list[str], citations):
        red = outline[:3] or ["必背结论待补充。"]
        blue = outline[3:6] or ["理解逻辑待补充。"]
        black = outline[6:9] or ["拓展提醒待补充。"]
        return [
            {"title": "红色：必背", "items": red, "citations": [c.model_dump() for c in citations]},
            {"title": "蓝色：理解", "items": blue, "citations": [c.model_dump() for c in citations]},
            {"title": "黑色：拓展", "items": black, "citations": [c.model_dump() for c in citations]},
        ]

