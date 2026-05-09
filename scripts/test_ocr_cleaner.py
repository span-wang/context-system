from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from library.ocr_cleaner import clean_parsed_document  # noqa: E402
from library.parser import ParsedBlock, ParsedDocument, ParsedPage  # noqa: E402


class OcrCleanerTests(unittest.TestCase):
    def test_removes_page_noise_and_repeated_footer(self) -> None:
        document = ParsedDocument(
            text="第1页\n单项选择题\nA. 甲 B. 乙 C. 丙 D. 丁\n版权所有\n",
            markdown="第1页\n单项选择题\nA. 甲 B. 乙 C. 丙 D. 丁\n版权所有\n",
            provider="pp_structure_v3",
            used_ocr=True,
            pages=[
                ParsedPage(page_number=1, text="第1页\n单项选择题\nA. 甲 B. 乙 C. 丙 D. 丁\n版权所有", markdown="同上"),
                ParsedPage(page_number=2, text="第2页\n答案：A\n版权所有", markdown="同上"),
            ],
        )

        cleaned = clean_parsed_document(document)

        self.assertNotIn("第1页", cleaned.text)
        self.assertNotIn("版权所有", cleaned.text)
        self.assertIn("A. 甲", cleaned.text)
        self.assertGreater(cleaned.cleanup_score or 0, 0)
        self.assertTrue(cleaned.cleanup_report.get("applied"))

    def test_splits_dense_options_and_solution_blocks(self) -> None:
        document = ParsedDocument(
            text="1. 下列说法正确的是（）。A. 甲B. 乙C. 丙D. 丁答案：A解析：因为甲正确。",
            markdown="1. 下列说法正确的是（）。A. 甲B. 乙C. 丙D. 丁答案：A解析：因为甲正确。",
            provider="legacy_cache",
            used_ocr=True,
            pages=[ParsedPage(page_number=1, text="1. 下列说法正确的是（）。A. 甲B. 乙C. 丙D. 丁答案：A解析：因为甲正确。")],
        )

        cleaned = clean_parsed_document(document, force=True)

        self.assertIn("A. 甲", cleaned.text)
        self.assertIn("B. 乙", cleaned.text)
        self.assertIn("答案:A", cleaned.text)
        self.assertIn("解析:因为甲正确。", cleaned.text)
        self.assertGreaterEqual(cleaned.cleanup_report.get("split_lines", 0), 4)

    def test_keeps_exam_without_answers_or_analysis(self) -> None:
        document = ParsedDocument(
            text="单项选择题\n1. 下列说法正确的是（）。\nA. 甲\nB. 乙\nC. 丙\nD. 丁",
            markdown="单项选择题\n1. 下列说法正确的是（）。\nA. 甲\nB. 乙\nC. 丙\nD. 丁",
            provider="legacy_cache",
            used_ocr=True,
            pages=[ParsedPage(page_number=1, text="单项选择题\n1. 下列说法正确的是（）。\nA. 甲\nB. 乙\nC. 丙\nD. 丁")],
        )

        cleaned = clean_parsed_document(document, force=True)

        self.assertIn("单项选择题", cleaned.text)
        self.assertIn("A. 甲", cleaned.text)
        self.assertNotIn("答案", cleaned.text)
        self.assertNotIn("解析", cleaned.text)

    def test_keeps_numeric_accounting_lines_and_trims_noise_prefix(self) -> None:
        document = ParsedDocument(
            text="借：银行存款\n113\n贷：主营业务收入100应交税费—应交增值税（销项税额）13\n微信扫描二维码,在线查看答案 贷：原材料85",
            markdown="借：银行存款\n113\n贷：主营业务收入100应交税费—应交增值税（销项税额）13\n微信扫描二维码,在线查看答案 贷：原材料85",
            provider="pp_structure_v3",
            used_ocr=True,
            pages=[ParsedPage(page_number=1, text="借：银行存款\n113\n贷：主营业务收入100应交税费—应交增值税（销项税额）13\n微信扫描二维码,在线查看答案 贷：原材料85")],
        )

        cleaned = clean_parsed_document(document, force=True)

        self.assertIn("113", cleaned.text)
        self.assertIn("贷:原材料85", cleaned.text)
        self.assertNotIn("微信扫描二维码", cleaned.text)

    def test_keeps_block_order_when_bbox_is_missing(self) -> None:
        document = ParsedDocument(
            text="",
            markdown="",
            provider="pp_structure_v3",
            used_ocr=True,
            pages=[
                ParsedPage(
                    page_number=1,
                    blocks=[
                        ParsedBlock(page_number=1, block_id="b1", text="1. 第一题"),
                        ParsedBlock(page_number=1, block_id="b2", text="A. 选项一"),
                        ParsedBlock(page_number=1, block_id="b3", text="2. 第二题"),
                    ],
                )
            ],
        )

        cleaned = clean_parsed_document(document, force=True)

        self.assertTrue(cleaned.text.startswith("1. 第一题"))
        self.assertIn("2. 第二题", cleaned.text)


if __name__ == "__main__":
    unittest.main()
