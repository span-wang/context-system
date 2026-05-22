from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.paper_ai_cleanup import (  # noqa: E402
    _normalize_ai_prediction_document,
    _request_ai_cleanup,
)


class PaperAICleanupGroupTests(unittest.TestCase):
    def test_normalize_prediction_document_keeps_grouped_questions(self) -> None:
        payload = _normalize_ai_prediction_document(
            {
                "sections": [
                    {
                        "title": "阅读理解",
                        "section_type": "material_analysis",
                        "questions": [
                            {
                                "question_no": "41-43",
                                "node_role": "group",
                                "question_type": "material_analysis",
                                "group_stem": "Read the following passage and answer questions 41 to 43.",
                                "material_text": "Passage body.",
                                "stem_text": "Read the following passage and answer questions 41 to 43.",
                                "source_raw_text": "Passage body and questions.",
                                "subquestions": [
                                    {
                                        "question_no": "41",
                                        "question_type": "single_choice",
                                        "stem_text": "Question one?",
                                        "options": ["A. One", "B. Two"],
                                        "answer_text": "A",
                                        "analysis_text": "Because one.",
                                        "source_raw_text": "41. Question one?",
                                    },
                                    {
                                        "question_no": "42",
                                        "question_type": "single_choice",
                                        "stem_text": "Question two?",
                                        "options": ["A. Alpha", "B. Beta"],
                                        "answer_text": "B",
                                        "analysis_text": "Because beta.",
                                        "source_raw_text": "42. Question two?",
                                    },
                                ],
                            }
                        ],
                    }
                ]
            }
        )

        self.assertEqual(payload["question_count"], 2)
        question = payload["sections"][0]["questions"][0]
        self.assertEqual(question["node_role"], "group")
        self.assertEqual(question["group_stem"], "Read the following passage and answer questions 41 to 43.")
        self.assertEqual(question["material_text"], "Passage body.")
        self.assertEqual(len(question["subquestions"]), 2)
        self.assertEqual(question["subquestions"][0]["node_role"], "subquestion")

    def test_request_prompt_requires_final_completion_and_standardization(self) -> None:
        class FakeProvider:
            def __init__(self) -> None:
                self.messages = None
                self.schema = None

            async def chat_json(self, messages, schema, **kwargs):
                self.messages = messages
                self.schema = schema
                return {"clean_text": "1. 题干\nA. 甲\nB. 乙"}

        class FakeEndpoint:
            system_prompt = "system"
            max_tokens = 1024

        provider = FakeProvider()
        asyncio.run(
            _request_ai_cleanup(
                provider,
                "1. 题干\nA. 甲\nB. 乙",
                endpoint=FakeEndpoint(),
                paper_name="测试卷",
                subject_name="测试学科",
                category_name="测试类目",
                chunk_index=1,
                chunk_count=1,
            )
        )

        self.assertIsNotNone(provider.messages)
        prompt = str(provider.messages[1]["content"])
        self.assertIn("直接输出可入库的最终结果", prompt)
        self.assertIn("若答案或解析缺失，必须先根据题干、选项、共用材料完成解题，再补全答案和解析", prompt)
        self.assertIn("输出 `prediction` 对象；该对象必须与系统当前 `prediction.json` 结构保持一致，并且内容就是最终结果", prompt)
        self.assertIn("`analysis_text` 必须结构化组织", prompt)
        question_schema = provider.schema["properties"]["prediction"]["properties"]["sections"]["items"]["properties"]["questions"]["items"]["properties"]
        self.assertIn("answer_text", question_schema)
        self.assertIn("analysis_text", question_schema)
        subquestion_schema = question_schema["subquestions"]["items"]["properties"]
        self.assertIn("answer_text", subquestion_schema)
        self.assertIn("analysis_text", subquestion_schema)
        self.assertIn("clean_text", provider.schema["properties"])

    def test_prompt_explicitly_requires_answer_analysis_completion(self) -> None:
        class FakeProvider:
            def __init__(self) -> None:
                self.messages = None

            async def chat_json(self, messages, schema, **kwargs):
                self.messages = messages
                return {"clean_text": "1. 题干\nA. 甲\nB. 乙"}

        class FakeEndpoint:
            system_prompt = "system"
            max_tokens = 1024

        provider = FakeProvider()
        asyncio.run(
            _request_ai_cleanup(
                provider,
                "1. 题干\nA. 甲\nB. 乙",
                endpoint=FakeEndpoint(),
                paper_name="无答案卷",
                subject_name="测试学科",
                category_name="测试类目",
                chunk_index=1,
                chunk_count=1,
            )
        )

        prompt = str(provider.messages[1]["content"])
        self.assertIn("若答案或解析缺失，必须先根据题干、选项、共用材料完成解题，再补全答案和解析", prompt)
        self.assertIn("补全出的答案与解析必须彼此一致", prompt)
        self.assertIn("解析必须逐项覆盖每个选项", prompt)

    def test_normalize_prediction_document_backfills_missing_source_raw_text(self) -> None:
        payload = _normalize_ai_prediction_document(
            {
                "sections": [
                    {
                        "title": "单项选择题",
                        "section_type": "single_choice",
                        "questions": [
                            {
                                "question_no": "1",
                                "question_type": "single_choice",
                                "stem_text": "题干",
                                "options": ["A. 甲", "B. 乙"],
                                "answer_text": "A",
                                "analysis_text": "",
                            }
                        ],
                    }
                ]
            }
        )

        question = payload["sections"][0]["questions"][0]
        self.assertEqual(question["source_raw_text"], "1. 题干\nA. 甲\nB. 乙\n答案：A")

if __name__ == "__main__":
    unittest.main()
