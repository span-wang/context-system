from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.papers import _split_paper_sections  # noqa: E402
from app.services.paper_parser_rules.engine import parse_sections_with_rules  # noqa: E402
from library.parser import ParsedBlock, ParsedDocument, ParsedPage  # noqa: E402


class PaperParserRulesP0HotfixTests(unittest.TestCase):
    def test_preserves_text_block_order_when_bbox_is_missing(self) -> None:
        document = ParsedDocument(
            text="",
            markdown="",
            provider="pp_structure_v3",
            used_ocr=True,
            pages=[
                ParsedPage(
                    page_number=1,
                    blocks=[
                        ParsedBlock(page_number=1, block_id="b1", text="综合题(共50分)"),
                        ParsedBlock(page_number=1, block_id="b2", text="26. 第一题"),
                        ParsedBlock(page_number=1, block_id="b3", text="A. 甲"),
                        ParsedBlock(page_number=1, block_id="b4", text="27. 第二题"),
                        ParsedBlock(page_number=1, block_id="b5", text="A. 乙"),
                    ],
                )
            ],
        )

        sections = parse_sections_with_rules(document)

        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].title, "综合题")
        self.assertEqual(len(sections[0].blocks), 2)
        self.assertTrue(sections[0].blocks[0].raw_text.startswith("26."))
        self.assertTrue(sections[0].blocks[1].raw_text.startswith("27."))

    def test_keeps_leading_questions_before_late_section_header(self) -> None:
        text = """
一、 选择题(共4分)
1. 第一题
A. 甲
B. 乙
2. 第二题
A. 丙
B. 丁
综合题(共50分)
26. 第三题
(1) 小问一
""".strip()

        sections = _split_paper_sections(None, text)

        self.assertEqual(len(sections), 2)
        self.assertEqual(sections[0].title, "选择题")
        self.assertEqual(sections[0].section_type, "single_choice")
        self.assertEqual(len(sections[0].blocks), 2)
        self.assertEqual(sections[1].title, "综合题")
        self.assertEqual(len(sections[1].blocks), 1)

    def test_splits_inline_question_number_after_option_tail(self) -> None:
        text = """
单项选择题
8. 第八题
A. 甲
B. 乙
C. 丙
D. 丁9. 第九题
A. 子项
B. 次项
""".strip()

        sections = _split_paper_sections(None, text)

        self.assertEqual(len(sections), 1)
        self.assertEqual(len(sections[0].blocks), 2)
        self.assertTrue(sections[0].blocks[0].raw_text.startswith("8."))
        self.assertTrue(sections[0].blocks[1].raw_text.startswith("9."))

    def test_splits_inline_question_number_after_prompt_range(self) -> None:
        text = """
综合题
26. 第一题
(1) 小问一
O 28. 第二题
材料一：图文材料
(1) 小问二
""".strip()

        sections = _split_paper_sections(None, text)

        self.assertEqual(len(sections), 1)
        self.assertEqual(len(sections[0].blocks), 1)
        self.assertTrue(sections[0].blocks[0].raw_text.startswith("26."))


if __name__ == "__main__":
    unittest.main()
