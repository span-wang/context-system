from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from library.ocr_cleaner import clean_parsed_document  # noqa: E402
from library.parser import ParsedDocument, ParsedPage  # noqa: E402


class PaperParserNoiseSectionTests(unittest.TestCase):
    def test_skips_low_signal_duplicate_section_before_specific_header(self) -> None:
        document = ParsedDocument(
            text="不定项选择题\n借：库存商品 10\n贷：原材料 10\n•\n不定项选择题01-存货\n根据资料①，下列各项中，说法正确的是（）。\nA. 选项一\nB. 选项二\nC. 选项三\nD. 选项四\n答案：A\n解析：解析。",
            markdown="不定项选择题\n借：库存商品 10\n贷：原材料 10\n•\n不定项选择题01-存货\n根据资料①，下列各项中，说法正确的是（）。\nA. 选项一\nB. 选项二\nC. 选项三\nD. 选项四\n答案：A\n解析：解析。",
            provider="pp_structure_v3",
            used_ocr=True,
            pages=[ParsedPage(page_number=1, text="不定项选择题\n借：库存商品 10\n贷：原材料 10\n•\n不定项选择题01-存货\n根据资料①，下列各项中，说法正确的是（）。\nA. 选项一\nB. 选项二\nC. 选项三\nD. 选项四\n答案：A\n解析：解析。")],
        )

        cleaned = clean_parsed_document(document, force=True)

        self.assertIn("不定项选择题01-存货", cleaned.text)
        self.assertIn("A. 选项一", cleaned.text)
        self.assertNotIn("•", cleaned.text)

    def test_keeps_numeric_accounting_amount_line(self) -> None:
        document = ParsedDocument(
            text="单项选择题\n借：银行存款\n113\n贷：主营业务收入100应交税费—应交增值税（销项税额）13\n1. 下列说法正确的是（）。\nA. 选项一\nB. 选项二\nC. 选项三\nD. 选项四",
            markdown="单项选择题\n借：银行存款\n113\n贷：主营业务收入100应交税费—应交增值税（销项税额）13\n1. 下列说法正确的是（）。\nA. 选项一\nB. 选项二\nC. 选项三\nD. 选项四",
            provider="pp_structure_v3",
            used_ocr=True,
            pages=[ParsedPage(page_number=1, text="单项选择题\n借：银行存款\n113\n贷：主营业务收入100应交税费—应交增值税（销项税额）13\n1. 下列说法正确的是（）。\nA. 选项一\nB. 选项二\nC. 选项三\nD. 选项四")],
        )

        cleaned = clean_parsed_document(document, force=True)

        self.assertIn("113", cleaned.text)
        self.assertIn("贷:主营业务收入100应交税费—应交增值税(销项税额)13", cleaned.text)


if __name__ == "__main__":
    unittest.main()
