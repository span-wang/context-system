from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from library.parser import (  # noqa: E402
    ParsedDocument,
    ParsedPage,
    _document_has_unresolved_formula_images,
)


class ParserFormulaFallbackTests(unittest.TestCase):
    def test_detects_unresolved_formula_image_placeholder(self) -> None:
        document = ParsedDocument(
            text="1. 计算下列算式。\nA. 900000÷(1-10%)×10%=100000(元）",
            markdown=(
                "1. 计算下列算式。\n\n"
                "A. 900000÷(1-10%)×10%=100000(元）\n\n"
                '<div style="text-align: center;"><img src="imgs/page_0001/img_in_formula_box_402_3278_1893_3328.jpg" alt="Image" /></div>'
            ),
            provider="pp_structure_v3",
            used_ocr=True,
            pages=[
                ParsedPage(
                    page_number=1,
                    markdown=(
                        "A. 900000÷(1-10%)×10%=100000(元）\n\n"
                        '<div style="text-align: center;"><img src="imgs/page_0001/img_in_formula_box_402_3278_1893_3328.jpg" alt="Image" /></div>'
                    ),
                )
            ],
        )

        self.assertTrue(_document_has_unresolved_formula_images(document))

    def test_ignores_normal_illustration_images(self) -> None:
        document = ParsedDocument(
            text="材料如图所示。",
            markdown='<img src="imgs/page_0001/img_in_image_box_1778_2368_2330_2748.jpg" alt="Image" />',
            provider="pp_structure_v3",
            used_ocr=True,
            pages=[ParsedPage(page_number=1, markdown='<img src="imgs/page_0001/img_in_image_box_1778_2368_2330_2748.jpg" alt="Image" />')],
        )

        self.assertFalse(_document_has_unresolved_formula_images(document))


if __name__ == "__main__":
    unittest.main()
