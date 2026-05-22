from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.question_bank import (  # noqa: E402
    _QuestionBankExportRecord,
    _QuestionBankExportSubquestionRecord,
    _normalize_export_options,
    _render_question_bank_markdown,
    _split_shared_stem,
)
from app.services.paper_review_ai import normalize_question_text  # noqa: E402


class QuestionBankExportTests(unittest.TestCase):
    def test_split_shared_stem_preserves_question_specific_body(self) -> None:
        shared, body = _split_shared_stem(
            "根据下列资料，回答下列问题。\n\n41. 根据资料一，下列说法正确的是（）。",
            "41. 根据资料一，下列说法正确的是（）。",
        )

        self.assertEqual(shared, "根据下列资料,回答下列问题。")
        self.assertEqual(body, normalize_question_text("41. 根据资料一，下列说法正确的是（）。"))

    def test_appendix_mode_renders_shared_material_once(self) -> None:
        records = [
            _QuestionBankExportRecord(
                question_no="41",
                question_type="single_choice",
                section_name="材料分析题",
                shared_stem="根据下列资料，回答下列问题。",
                material_text="",
                stem_text="根据资料一，下列说法正确的是（）。",
                options=["A. 选项一", "B. 选项二"],
                answer_text="A",
                analysis_text="解析一。",
                subquestions=[],
            ),
            _QuestionBankExportRecord(
                question_no="42",
                question_type="single_choice",
                section_name="材料分析题",
                shared_stem="根据下列资料，回答下列问题。",
                material_text="",
                stem_text="根据资料二，下列说法正确的是（）。",
                options=["A. 选项甲", "B. 选项乙"],
                answer_text="B",
                analysis_text="解析二。",
                subquestions=[],
            ),
        ]

        markdown = _render_question_bank_markdown(
            paper_name="2026 模拟卷",
            records=records,
            solution_mode="appendix",
        )

        self.assertEqual(markdown.count("### 共用材料"), 1)
        self.assertNotIn("## 题目", markdown)
        self.assertIn("## 单选题", markdown)
        self.assertIn("第41题 根据资料一，下列说法正确的是（）。", markdown)
        self.assertIn("第42题 根据资料二，下列说法正确的是（）。", markdown)
        self.assertIn("## 答案与解析", markdown)
        self.assertIn(":::answer-block 第41题", markdown)
        self.assertIn(":::answer-block 第42题", markdown)
        self.assertIn("答案：A", markdown)
        self.assertIn("答案：B", markdown)
        self.assertLess(markdown.find("第41题 根据资料一，下列说法正确的是（）。"), markdown.find("## 答案与解析"))
        self.assertLess(markdown.find("## 答案与解析"), markdown.find(":::answer-block 第41题"))

    def test_inline_mode_places_solution_after_each_question(self) -> None:
        records = [
            _QuestionBankExportRecord(
                question_no="1",
                question_type="single_choice",
                section_name="单项选择题",
                shared_stem="",
                material_text="",
                stem_text="下列说法正确的是（）。",
                options=["A. 甲", "B. 乙"],
                answer_text="A",
                analysis_text="因为甲正确。",
                subquestions=[],
            )
        ]

        markdown = _render_question_bank_markdown(
            paper_name="2026 模拟卷",
            records=records,
            solution_mode="inline",
        )

        self.assertNotIn("## 答案与解析", markdown)
        self.assertIn("## 单项选择题", markdown)
        self.assertIn("第1题 下列说法正确的是（）。", markdown)
        self.assertIn(":::answer-block", markdown)
        self.assertNotIn(":::answer-block 第1题", markdown)
        self.assertIn("答案：A", markdown)
        self.assertIn("解析：因为甲正确。", markdown)
        self.assertNotIn("**答案：**", markdown)
        self.assertLess(markdown.find("第1题 下列说法正确的是（）。"), markdown.find("答案：A"))

    def test_export_options_add_labels_once_for_clean_or_legacy_values(self) -> None:
        self.assertEqual(
            _normalize_export_options(["360", "318"]),
            ["A. 360", "B. 318"],
        )
        self.assertEqual(
            _normalize_export_options(["A. 360", "B、318", "C) 300"]),
            ["A. 360", "B. 318", "C. 300"],
        )

    def test_group_mode_renders_material_once_and_subquestions(self) -> None:
        records = [
            _QuestionBankExportRecord(
                question_no="41-43",
                question_type="material_analysis",
                section_name="阅读理解",
                shared_stem="Read the following passage and answer questions 41 to 43.",
                material_text="Passage content.",
                stem_text="",
                options=[],
                answer_text=None,
                analysis_text=None,
                subquestions=[
                    _QuestionBankExportSubquestionRecord(
                        question_no="41",
                        question_type="single_choice",
                        stem_text="Question one?",
                        options=["A. One", "B. Two"],
                        answer_text="A",
                        analysis_text="Because one.",
                    ),
                    _QuestionBankExportSubquestionRecord(
                        question_no="42",
                        question_type="single_choice",
                        stem_text="Question two?",
                        options=["A. Alpha", "B. Beta"],
                        answer_text="B",
                        analysis_text="Because beta.",
                    ),
                ],
            ),
        ]

        markdown = _render_question_bank_markdown(
            paper_name="2026 阅读卷",
            records=records,
            solution_mode="appendix",
        )

        self.assertIn("## 材料题", markdown)
        self.assertIn("### 共用材料", markdown)
        self.assertIn("Read the following passage and answer questions 41 to 43.", markdown)
        self.assertIn("材料：", markdown)
        self.assertIn("Passage content.", markdown)
        self.assertIn("第41题 Question one?", markdown)
        self.assertIn("第42题 Question two?", markdown)
        self.assertIn("## 答案与解析", markdown)
        self.assertIn(":::answer-block 第41题", markdown)
        self.assertIn(":::answer-block 第42题", markdown)


if __name__ == "__main__":
    unittest.main()
