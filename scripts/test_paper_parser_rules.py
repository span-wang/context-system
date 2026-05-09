from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.papers import _parse_question_block, _split_paper_sections  # noqa: E402
from app.services.paper_parser_rules import parse_sections_with_rules  # noqa: E402
from library.parser import ParsedBlock, ParsedDocument, ParsedPage  # noqa: E402


class PaperParserRuleTests(unittest.TestCase):
    def test_extracts_multiline_options_answer_and_analysis(self) -> None:
        text = """
单项选择题
1. 下列说法正确的是（）。
A. 第一项第一行
第二行
B. 第二项
C. 第三项
D. 第四项
正确答案：B
答案解析：这是解析。
""".strip()
        section = _split_paper_sections(None, text)[0]
        parsed = _parse_question_block(section.blocks[0], section)

        self.assertEqual(parsed.options_json, ["A. 第一项第一行 第二行", "B. 第二项", "C. 第三项", "D. 第四项"])
        self.assertEqual(parsed.answer_text, "B")
        self.assertEqual(parsed.analysis_text, "这是解析。")

    def test_extracts_inline_options(self) -> None:
        text = """
单项选择题
1. 下列说法正确的是（）。A. 甲 B. 乙 C. 丙 D. 丁 答案：C 解析：因为丙正确。
""".strip()
        section = _split_paper_sections(None, text)[0]
        parsed = _parse_question_block(section.blocks[0], section)

        self.assertEqual(parsed.options_json, ["A. 甲", "B. 乙", "C. 丙", "D. 丁"])
        self.assertEqual(parsed.answer_text, "C")
        self.assertEqual(parsed.analysis_text, "因为丙正确。")

    def test_extracts_tightly_joined_inline_options_after_chinese_text(self) -> None:
        text = """
单项选择题
1. 下列各项中,属于对企业会计核算空间范围所作的合理假设的是(). A.会计主体B.会计分期C.货币计量D.持续经营
""".strip()
        section = _split_paper_sections(None, text)[0]
        parsed = _parse_question_block(section.blocks[0], section)

        self.assertEqual(parsed.stem_text, "下列各项中,属于对企业会计核算空间范围所作的合理假设的是().")
        self.assertEqual(parsed.options_json, ["A. 会计主体", "B. 会计分期", "C. 货币计量", "D. 持续经营"])

    def test_strips_trailing_option_hint_from_stem(self) -> None:
        text = """
单项选择题
1. 下列规范性文件中，效力最高的是C
A. 全国人民代表大会发布的《中华人民共和国民法典》
B. 财政部发布的《会计基础工作规范》
C. 国务院发布的《中华人民共和国企业所得税法实施条例》
D. 北京市人民代表大会发布的《北京市制定地方性法规条例》
正确答案：A
答案解析：解析。
""".strip()
        section = _split_paper_sections(None, text)[0]
        parsed = _parse_question_block(section.blocks[0], section)

        self.assertEqual(parsed.stem_text, "下列规范性文件中，效力最高的是")
        self.assertEqual(parsed.options_json[0], "A. 全国人民代表大会发布的《中华人民共和国民法典》")

    def test_preserves_body_only_answer_letter_when_options_exist(self) -> None:
        text = """
单项选择题
1. 下列说法正确的是（）。
A. 第一项第一行
第二行
B. 第二项
C. 第三项
D. 第四项
正确答案：B
答案解析：这是解析。
""".strip()
        section = _split_paper_sections(None, text)[0]
        parsed = _parse_question_block(section.blocks[0], section)

        self.assertEqual(parsed.stem_text, "下列说法正确的是（）。")
        self.assertEqual(parsed.options_json, ["A. 第一项第一行 第二行", "B. 第二项", "C. 第三项", "D. 第四项"])

    def test_applies_shared_stem_to_non_one_based_question_sequence(self) -> None:
        text = """
案例分析题
甲公司发生如下事项：
资料一：采购原材料。
资料二：销售库存商品。
要求：根据上述资料，回答下列小题。
41. 根据资料一，下列说法正确的是（）。
A. 选项一
B. 选项二
C. 选项三
D. 选项四
答案：A
解析：解析一。
42. 根据资料二，下列说法正确的是（）。
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

        self.assertIn("甲公司发生如下事项", first.stem_text)
        self.assertIn("甲公司发生如下事项", second.stem_text)
        self.assertEqual(first.question_no, "41")
        self.assertEqual(second.question_no, "42")

    def test_counts_di_xiao_ti_as_subquestions(self) -> None:
        text = """
案例分析题
1. 根据资料，回答下列问题。
第1小题 计算销售额。
第2小题 计算销项税额。
答案：略
解析：略
""".strip()
        section = _split_paper_sections(None, text)[0]
        parsed = _parse_question_block(section.blocks[0], section)

        self.assertEqual(parsed.subquestion_count, 2)
        self.assertEqual(parsed.question_type, "case_analysis")

    def test_p0_rule_engine_splits_basic_sections_and_questions(self) -> None:
        document = ParsedDocument(
            text="",
            markdown="",
            provider="test",
            pages=[
                ParsedPage(
                    page_number=1,
                    width=1000,
                    height=1400,
                    blocks=[
                        ParsedBlock(page_number=1, block_id="b1", text="单项选择题", bbox=[80, 100, 280, 130]),
                        ParsedBlock(page_number=1, block_id="b2", text="1. 下列说法正确的是（）。", bbox=[80, 180, 540, 220]),
                        ParsedBlock(page_number=1, block_id="b3", text="A. 甲", bbox=[120, 240, 260, 270]),
                        ParsedBlock(page_number=1, block_id="b4", text="B. 乙", bbox=[120, 285, 260, 315]),
                        ParsedBlock(page_number=1, block_id="b5", text="C. 丙", bbox=[120, 330, 260, 360]),
                        ParsedBlock(page_number=1, block_id="b6", text="D. 丁", bbox=[120, 375, 260, 405]),
                        ParsedBlock(page_number=1, block_id="b7", text="2. 下列处理正确的是（）。", bbox=[80, 455, 540, 495]),
                        ParsedBlock(page_number=1, block_id="b8", text="A. 选项一", bbox=[120, 515, 300, 545]),
                        ParsedBlock(page_number=1, block_id="b9", text="B. 选项二", bbox=[120, 560, 300, 590]),
                    ],
                )
            ],
        )

        sections = parse_sections_with_rules(document)

        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].title, "单项选择题")
        self.assertEqual(len(sections[0].blocks), 2)
        self.assertTrue(sections[0].blocks[0].raw_text.startswith("1."))
        self.assertTrue(sections[0].blocks[1].raw_text.startswith("2."))

    def test_p0_rule_engine_preserves_shared_context(self) -> None:
        document = ParsedDocument(
            text="",
            markdown="",
            provider="test",
            pages=[
                ParsedPage(
                    page_number=1,
                    width=1000,
                    height=1400,
                    blocks=[
                        ParsedBlock(page_number=1, block_id="b1", text="案例分析题", bbox=[80, 100, 280, 130]),
                        ParsedBlock(page_number=1, block_id="b2", text="根据下列资料，回答下列小题。", bbox=[80, 180, 560, 220]),
                        ParsedBlock(page_number=1, block_id="b3", text="资料一：采购原材料。", bbox=[80, 225, 520, 255]),
                        ParsedBlock(page_number=1, block_id="b4", text="资料二：销售库存商品。", bbox=[80, 260, 520, 290]),
                        ParsedBlock(page_number=1, block_id="b5", text="41. 根据资料一，下列说法正确的是（）。", bbox=[80, 340, 680, 380]),
                        ParsedBlock(page_number=1, block_id="b6", text="A. 选项一", bbox=[120, 400, 300, 430]),
                        ParsedBlock(page_number=1, block_id="b7", text="B. 选项二", bbox=[120, 445, 300, 475]),
                        ParsedBlock(page_number=1, block_id="b8", text="42. 根据资料二，下列说法正确的是（）。", bbox=[80, 520, 680, 560]),
                        ParsedBlock(page_number=1, block_id="b9", text="A. 选项甲", bbox=[120, 580, 300, 610]),
                        ParsedBlock(page_number=1, block_id="b10", text="B. 选项乙", bbox=[120, 625, 300, 655]),
                    ],
                )
            ],
        )

        sections = parse_sections_with_rules(document)

        self.assertEqual(len(sections), 1)
        self.assertEqual(len(sections[0].blocks), 2)
        self.assertIn("根据下列资料", sections[0].blocks[0].stem_prefix or "")
        self.assertIn("根据下列资料", sections[0].blocks[1].stem_prefix or "")

    def test_ocr_markdown_answers_and_html_noise(self) -> None:
        text = """
## 第1章

## 单项选择题

0

1.下列各项中，属于对企业会计核算空间范围所作的合理假设的是（）。

A.会计主体B.会计分期C.货币计量D.持续经营

## 答案与解析

正确答案：A

答案解析

会计主体，是指会计工作服务的特定对象，是企业会计确认、计量、记录和报告的空间范围。

2.下列选项中，既是会计主体又是法律主体的是（）。

A.企业集团

B.分公司

C.子公司

D.公司的财务部门

## 答案与解析

正确答案：C

答案解析

会计主体指会计服务的特定对象，是企业会计确认、计量、记录和报告的空间范围。会计主体与法律主体（法人）并非是对等的概念。

<div style="text-align: center;"><html><body><table border="1"><tr><td>公司类型</td><td>会计主体</td><td>法律主体</td></tr><tr><td>总公司</td><td></td><td></td></tr><tr><td>分公司</td><td></td><td></td></tr><tr><td>母公司</td><td></td><td></td></tr><tr><td>子公司</td><td></td><td></td></tr><tr><td>企业集团</td><td></td><td>×</td></tr></table></body></html></div>

3.下列经济业务中，按照权责发生制应计入当期收入或费用的是（）。

A.收到客户预付下月货款

B.预付下季度办公楼租金

C.本月销售商品一批，货款尚未收回

D.本月收到上个月销售货款

## 答案与解析

正确答案：C

答案解析

权责发生制是以取得收钱的权利或产生付钱的义务为标志来确定本期收入和费用的会计核算基础。

### 4. 在不同会计期间发生的相同或相似的交易或事项，应当采用一致的会计政策，不得随意变更。下列各项中，对这一会计信息质量要求表述正确的是（）。

A.谨慎性B.重要性C.可比性D.可理解性

## 答案与解析

正确答案：C

答案解析

选项A，谨慎性要求企业对交易或者事项进行会计确认、计量、记录和报告应当保持应有的谨慎。

## 多项选择题

1.下列各项中，关于会计职能的表述正确的有（）。

A.监督职能是核算职能的保障

B.核算与监督是基本职能

C.核算职能是监督职能的基础

D.预测经济前景、参与经济决策和评价经营业绩是拓展职能

## 答案与解析

正确答案：A,B,C,D

答案解析

会计核算与会计监督是相辅相成、辩证统一的。
""".strip()
        sections = _split_paper_sections(None, text)

        self.assertEqual(len(sections), 2)
        self.assertEqual(sections[0].title, "单项选择题")
        self.assertEqual(sections[1].title, "多项选择题")
        self.assertEqual(len(sections[0].blocks), 4)
        self.assertEqual(len(sections[1].blocks), 1)

        first = _parse_question_block(sections[0].blocks[0], sections[0])
        fourth = _parse_question_block(sections[0].blocks[3], sections[0])
        multi = _parse_question_block(sections[1].blocks[0], sections[1])

        self.assertEqual(first.question_no, "1")
        self.assertEqual(first.stem_text, "下列各项中，属于对企业会计核算空间范围所作的合理假设的是（）。")
        self.assertEqual(first.options_json, ["A. 会计主体", "B. 会计分期", "C. 货币计量", "D. 持续经营"])
        self.assertEqual(first.answer_text, "A")
        self.assertTrue((first.analysis_text or "").startswith("会计主体，是指会计工作服务的特定对象"))

        self.assertEqual(fourth.question_no, "4")
        self.assertEqual(fourth.answer_text, "C")
        self.assertEqual(fourth.options_json, ["A. 谨慎性", "B. 重要性", "C. 可比性", "D. 可理解性"])

        self.assertEqual(multi.question_type, "multiple_choice")
        self.assertEqual(multi.question_no, "1")
        self.assertEqual(multi.answer_text, "A,B,C,D")
        self.assertEqual(len(multi.options_json), 4)

    def test_real_paper_000001_source_regression(self) -> None:
        source_path = ROOT / "data" / "paper_parser_dataset" / "paper_000001_paper" / "source.txt"
        if not source_path.exists():
            self.skipTest("real paper sample not found")
        text = source_path.read_text(encoding="utf-8")

        sections = _split_paper_sections(None, text)
        parsed = [(section, _parse_question_block(block, section)) for section in sections for block in section.blocks]

        self.assertEqual(len(sections), 6)

        multi_q2 = next(
            question for section, question in parsed
            if section.title == "多项选择题" and section.sort_order == 2 and question.question_no == "2"
        )
        self.assertEqual(multi_q2.stem_text, "下列各项中，关于会计职能说法正确的有（）。")

        judge_q2 = next(
            question for section, question in parsed
            if section.title == "判断题" and section.sort_order == 3 and question.question_no == "2"
        )
        self.assertNotIn("第2章", judge_q2.analysis_text or "")

        chapter2_multi_q2 = next(
            question for section, question in parsed
            if section.title == "多项选择题" and section.sort_order == 5 and question.question_no == "2"
        )
        self.assertEqual(chapter2_multi_q2.question_type, "multiple_choice")
        self.assertEqual(chapter2_multi_q2.options_json, ["C. 应付债券", "D. 预收款项"])

    def test_real_paper_000005_source_regression(self) -> None:
        source_path = ROOT / "data" / "paper_parser_dataset" / "paper_000005_paper" / "source.txt"
        if not source_path.exists():
            self.skipTest("real paper sample not found")
        text = source_path.read_text(encoding="utf-8")

        sections = _split_paper_sections(None, text)
        parsed = [(section, _parse_question_block(block, section)) for section in sections for block in section.blocks]

        self.assertEqual(len(sections), 2)
        self.assertEqual((sections[0].title, sections[0].section_type, len(sections[0].blocks)), ("单项选择题", "single_choice", 70))
        self.assertEqual((sections[1].title, sections[1].section_type, len(sections[1].blocks)), ("多项选择题", "multiple_choice", 15))

        first = parsed[0][1]
        self.assertEqual(first.question_no, "1")
        self.assertTrue(first.stem_text.startswith("某企业针对重大安全隐患编制了安全技术措施计划"))
        self.assertNotIn("2021注安《管理》真题", first.stem_text)
        self.assertNotIn("单项选择题", first.stem_text)

        multi_first = next(
            question for section, question in parsed
            if section.title == "多项选择题" and question.question_no == "71"
        )
        self.assertEqual(multi_first.question_type, "multiple_choice")
        self.assertEqual(len(multi_first.options_json), 5)

    def test_splits_numbered_section_headers_with_exam_instructions(self) -> None:
        text = """
2021注安《管理》真题
一、 单项选择题(共70题，每题1分，共70分。每题的备选项中，只有1个最符合题意)
1.某企业针对重大安全隐患编制了安全技术措施计划。负责审查、核定安全技术措施计划的召集人是()。
A.总工程师B.主管安全生产领导C.单位主要负责人D.主管财务领导
二、多项选择题(共15题，每题2分。每题的备选项中，有2个或2个以上符合题意，至少有1个错项。错选，本题不得分；少选，所选的每个选项得0.5分)
71.关于安全带使用要求的说法，正确的有()。
A.高挂低用B.应定期检查C.破损后可继续使用D.应按规范佩戴E.超过年限应报废
""".strip()

        sections = _split_paper_sections(None, text)

        self.assertEqual(len(sections), 2)
        self.assertEqual(sections[0].title, "单项选择题")
        self.assertEqual(sections[0].section_type, "single_choice")
        self.assertEqual(sections[1].title, "多项选择题")
        self.assertEqual(sections[1].section_type, "multiple_choice")

        first = _parse_question_block(sections[0].blocks[0], sections[0])
        multi = _parse_question_block(sections[1].blocks[0], sections[1])

        self.assertEqual(first.stem_text, "某企业针对重大安全隐患编制了安全技术措施计划。负责审查、核定安全技术措施计划的召集人是()。")
        self.assertEqual(first.options_json, ["A. 总工程师", "B. 主管安全生产领导", "C. 单位主要负责人", "D. 主管财务领导"])
        self.assertEqual(first.question_type, "single_choice")

        self.assertEqual(multi.question_no, "71")
        self.assertEqual(multi.question_type, "multiple_choice")
        self.assertEqual(
            multi.options_json,
            ["A. 高挂低用", "B. 应定期检查", "C. 破损后可继续使用", "D. 应按规范佩戴", "E. 超过年限应报废"],
        )


if __name__ == "__main__":
    unittest.main()
