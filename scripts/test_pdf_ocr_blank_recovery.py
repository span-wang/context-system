from __future__ import annotations

import sys
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.papers import _parse_question_block, _split_paper_sections  # noqa: E402
from app.services.question_enrichment import normalize_question_text  # noqa: E402
from library.pdf_ocr_pipeline import OCRPageResult, OCRTextBlock, _attach_blank_line_placeholders  # noqa: E402


class PdfOcrBlankRecoveryTests(unittest.TestCase):
    def test_detects_blank_line_placeholders_from_image(self) -> None:
        image = Image.new("RGB", (320, 220), "white")
        draw = ImageDraw.Draw(image)
        draw.line((90, 120, 240, 120), fill="black", width=2)

        page = OCRPageResult(
            page_number=1,
            width=320,
            height=220,
            text="",
            markdown="",
            blocks=[
                OCRTextBlock(
                    page_number=1,
                    block_id="p1-b1",
                    text="根据材料填写",
                    bbox=[20, 100, 120, 130],
                )
            ],
        )

        _attach_blank_line_placeholders(page, image)

        self.assertTrue(any(block.block_type == "blank" for block in page.blocks))
        self.assertIn("（ ）", "\n".join(block.text for block in page.blocks))

    def test_blank_placeholder_survives_normalization_and_becomes_fill_blank(self) -> None:
        text = """
填空题
1. 太阳系中最大的行星是（ ）。
答案：木星
解析：略。
""".strip()
        section = _split_paper_sections(None, text)[0]
        parsed = _parse_question_block(section.blocks[0], section)

        self.assertEqual(parsed.question_type, "fill_blank")
        self.assertIn("（ ）", normalize_question_text("（ ）"))


if __name__ == "__main__":
    unittest.main()
