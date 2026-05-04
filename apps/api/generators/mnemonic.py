from schemas.context import GenerationContext

from .base import TemplateGenerator


class MnemonicGenerator(TemplateGenerator):
    content_type = "mnemonic"
    heading = "口诀速记"

    def _sections(self, context: GenerationContext, outline: list[str], citations):
        keyword = context.chapter or context.category or context.subject
        mnemonic = "、".join([item[:4] for item in outline[:4]]).replace(" ", "")
        if not mnemonic:
            mnemonic = f"{keyword}先框架、后细节、再真题"
        return [
            {
                "title": "记忆口诀",
                "items": [f"{keyword}：{mnemonic}"],
                "citations": [c.model_dump() for c in citations],
            },
            {
                "title": "拆解说明",
                "items": outline[:6],
                "citations": [c.model_dump() for c in citations],
            },
        ]

