from schemas.context import GenerationContext

from .base import TemplateGenerator


class ExamReviewGenerator(TemplateGenerator):
    content_type = "exam_review"
    heading = "真题串讲"

    def _sections(self, context: GenerationContext, outline: list[str], citations):
        questions = []
        for index, item in enumerate(outline[:6], 1):
            questions.append(
                f"题 {index}：围绕“{item[:36]}”设问；答案要点：定位概念、列条件、写结论。"
            )
        if not questions:
            questions = ["题 1：请上传真题或教材资料后生成更准确的串讲。"]
        return [{"title": "题目与知识点串联", "items": questions, "citations": [c.model_dump() for c in citations]}]

