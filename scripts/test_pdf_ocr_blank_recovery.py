from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.papers import _parse_question_block, _split_paper_sections  # noqa: E402
from app.services.paper_review_ai import normalize_question_text  # noqa: E402
from library.pdf_ocr_pipeline import (  # noqa: E402
    OCRPageResult,
    OCRPipelineOptions,
    OCRTextBlock,
    _attach_blank_line_placeholders,
    _get_pdf_ocr_checkpoint_dir,
    _ocr_page_result_to_dict,
    run_pdf_ocr_pipeline,
)


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

    def test_reuses_cached_pages_when_pdf_rendering_is_unavailable(self) -> None:
        pdf_bytes = b"%PDF-1.4 cached"
        options = OCRPipelineOptions(force_ocr=True, cache_namespace="paper_asset_test")

        with tempfile.TemporaryDirectory() as tmp_dir:
            checkpoint_root = Path(tmp_dir)
            checkpoint_dir = _get_pdf_ocr_checkpoint_dir(pdf_bytes, options, checkpoint_root)
            page = OCRPageResult(
                page_number=1,
                width=320,
                height=240,
                text="第1小题\nA.495\n答案解析",
                markdown="第1小题\n\nA.495\n\n答案解析",
                blocks=[
                    OCRTextBlock(page_number=1, block_id="p1-b1", text="第1小题"),
                    OCRTextBlock(page_number=1, block_id="p1-b2", text="A.495"),
                    OCRTextBlock(page_number=1, block_id="p1-b3", text="答案解析"),
                ],
            )
            (checkpoint_dir / "page_00001.json").write_text(
                json.dumps(_ocr_page_result_to_dict(page), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            with patch("library.pdf_ocr_pipeline._get_pdf_ocr_checkpoint_root", return_value=checkpoint_root):
                with patch("library.pdf_ocr_pipeline._get_pdf_page_count", side_effect=RuntimeError("fitz missing")):
                    result = run_pdf_ocr_pipeline(pdf_bytes, "sample.pdf", options=options)

            self.assertTrue(result.used_ocr)
            self.assertEqual(result.provider, "pdf_ocr_pipeline/checkpoint")
            self.assertIn("A.495", result.text)
            self.assertIn("Unable to render PDF pages", " ".join(result.warnings))


if __name__ == "__main__":
    unittest.main()
