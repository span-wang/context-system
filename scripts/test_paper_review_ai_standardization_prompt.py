from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.paper_review_ai import _request_question_standardization, normalize_options  # noqa: E402


class PaperReviewAIStandardizationPromptTests(unittest.TestCase):
    def test_normalize_options_strips_choice_labels_from_storage_values(self) -> None:
        self.assertEqual(
            normalize_options(["A. 360", "B、318", "C) 300", "D 378"], "single_choice"),
            ["360", "318", "300", "378"],
        )

    def test_prompt_restricts_answer_basis_and_requires_option_level_analysis(self) -> None:
        class FakeProvider:
            def __init__(self) -> None:
                self.messages = None
                self.schema = None

            async def chat_json(self, messages, schema, **kwargs):
                self.messages = messages
                self.schema = schema
                return {
                    "normalized_stem": "题干",
                    "normalized_options": ["A. 甲", "B. 乙"],
                    "answer": "A",
                    "analysis": "因为甲符合题意。",
                }

        provider = FakeProvider()
        question = SimpleNamespace(
            node_role="standalone",
            question_type="single_choice",
            stem_text="1. 题干",
            options_json=["A. 甲", "B. 乙"],
            answer_text=None,
            analysis_text=None,
            group_stem=None,
            material_text=None,
            subquestions=[],
        )

        asyncio.run(
            _request_question_standardization(
                provider,
                question=question,
                subject_name="测试学科",
                category_name="测试类目",
                max_tokens=1024,
            )
        )

        self.assertIsNotNone(provider.messages)
        system_prompt = str(provider.messages[0]["content"])
        user_prompt = str(provider.messages[1]["content"])
        self.assertIn("必须基于题干、选项、共用材料先完成作答", system_prompt)
        self.assertIn("只能依据当前学科类目的教材或教辅中的通行内容", system_prompt)
        self.assertIn("若答案或解析缺失，必须先根据题干、选项、共用材料完成解题，再补全答案和解析", user_prompt)
        self.assertIn("除非题干、选项或材料本身严重缺失到无法作答，否则不允许留空", user_prompt)
        self.assertIn("补全出的答案与解析必须彼此一致", user_prompt)
        self.assertIn("解析必须逐项覆盖每个选项", user_prompt)
        self.assertIn("明确写出每个选项为什么对或为什么错", user_prompt)
        self.assertIn("`analysis` 必须结构化组织", user_prompt)
        self.assertIn("考察知识点（考察的是什么）", user_prompt)
        self.assertIn("计算题要拆成步骤，把常识转成动作流", user_prompt)
        self.assertIn("遇到易混概念要做辨析", user_prompt)
        self.assertIn("给套路，但不能脱离本题空泛套模板", user_prompt)
        self.assertIn("答案与解析的依据只允许来自当前学科类目的教材或教辅", user_prompt)
        self.assertIn("类目：测试类目", user_prompt)
        self.assertNotIn("尽量补全；不确定时保持为空", user_prompt)
        self.assertIn("解析要结构化表达，并按题目实际情况选择知识点、步骤、辨析、套路等模块", system_prompt)
        self.assertEqual(provider.schema["required"], ["normalized_stem", "normalized_options", "answer", "analysis"])


if __name__ == "__main__":
    unittest.main()
