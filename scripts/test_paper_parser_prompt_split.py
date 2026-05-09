from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.papers import _parse_question_block, _split_paper_sections  # noqa: E402


class PaperParserPromptSplitTests(unittest.TestCase):
    def test_splits_prompt_based_questions_without_explicit_numbers(self) -> None:
        text = """
不定项选择题
甲公司发生如下事项：
要求：根据上述资料，回答下列小题。
根据资料①，下列各项中，说法正确的是（）。
A. 选项一
B. 选项二
C. 选项三
D. 选项四
答案：A,C
解析：解析一。
根据资料②，下列各项中，说法正确的是（）。
A. 选项甲
B. 选项乙
C. 选项丙
D. 选项丁
答案：D
解析：解析二。
""".strip()
        section = _split_paper_sections(None, text)[0]
        first = _parse_question_block(section.blocks[0], section)
        second = _parse_question_block(section.blocks[1], section)

        self.assertEqual(len(section.blocks), 2)
        self.assertEqual(first.question_no, "1")
        self.assertEqual(second.question_no, "2")
        self.assertEqual(first.answer_text, "A,C")
        self.assertEqual(second.answer_text, "D")
        self.assertIn("甲公司发生如下事项", first.stem_text)
        self.assertIn("甲公司发生如下事项", second.stem_text)

    def test_attaches_appendix_answers_and_analysis_to_questions(self) -> None:
        text = """
单项选择题
1. 下列说法正确的是（）。
A. 甲
B. 乙
C. 丙
D. 丁
2. 下列处理正确的是（）。
A. 选项一
B. 选项二
C. 选项三
D. 选项四

答案与解析
1. 正确答案：A
解析：解析一。
2. 正确答案：C
解析：解析二。
""".strip()
        section = _split_paper_sections(None, text)[0]
        first = _parse_question_block(section.blocks[0], section)
        second = _parse_question_block(section.blocks[1], section)

        self.assertEqual(first.answer_text, "A")
        self.assertEqual(first.analysis_text, "解析一。")
        self.assertEqual(second.answer_text, "C")
        self.assertEqual(second.analysis_text, "解析二。")

    def test_avoids_treating_decimal_option_values_as_question_numbers(self) -> None:
        text = """
不定项选择题01-交易性金融资产
甲公司为增值税一般纳税人，发生如下业务：
要求：根据上述资料，回答下列小题。
根据资料1，下列各项中甲公司购买股票应计入“交易性金融资产--成本”科目的金额正确的是()万元。
A. 495
B. 501.25
C. 500
D. 501.325
答案：A
解析：解析一。
根据资料2，下列各项中，甲公司收到现金股利的会计处理正确的是()。
A. 选项一
B. 选项二
C. 选项三
D. 选项四
答案：D
解析：解析二。
""".strip()

        section = _split_paper_sections(None, text)[0]
        first = _parse_question_block(section.blocks[0], section)
        second = _parse_question_block(section.blocks[1], section)

        self.assertEqual(len(section.blocks), 2)
        self.assertEqual(first.question_no, "1")
        self.assertEqual(second.question_no, "2")
        self.assertEqual(first.options_json, ["A. 495", "B. 501.25", "C. 500", "D. 501.325"])
        self.assertEqual(first.answer_text, "A")
        self.assertEqual(second.answer_text, "D")

    def test_splits_material_groups_by_inline_group_header(self) -> None:
        text = """
根据资料1至5,下列各项中,该股票投资对甲公司2026年度营业利润的影响额是()万元。
A. 108.09
B. 113.75
C. 118.75
D. 98.09
答案：A
解析：解析一。 不定项选择题02-坏账准备
甲公司采用备抵法核算应收账款减值。
要求：不考虑其他因素，回答下列小题。
根据资料1，下列各项中，甲公司销售商品的会计处理正确的是()。
A. 选项一
B. 选项二
C. 选项三
D. 选项四
答案：B,D
解析：解析二。
""".strip()

        sections = _split_paper_sections(None, text)

        self.assertEqual(len(sections), 2)
        self.assertEqual(sections[0].title, "自动切题")
        self.assertEqual(sections[1].title, "不定项选择题")
        self.assertEqual(len(sections[1].blocks), 1)
        second = _parse_question_block(sections[1].blocks[0], sections[1])
        self.assertEqual(second.question_no, "1")
        self.assertEqual(second.answer_text, "B,D")


if __name__ == "__main__":
    unittest.main()
