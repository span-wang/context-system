from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from library.parse_options import (  # noqa: E402
    PRIMARY_PARSE_PRESETS,
    DocumentParseOptions,
    build_document_parse_options,
    get_parse_capability_payload,
)


class ParseCapabilityTests(unittest.TestCase):
    def test_parse_capability_payload_exposes_primary_paddle_presets_first(self) -> None:
        payload = get_parse_capability_payload()
        presets = payload["presets"]
        primary_values = [preset["value"] for preset in presets if preset["primary"]]

        self.assertEqual(primary_values, list(PRIMARY_PARSE_PRESETS))
        self.assertEqual(presets[0]["value"], "vl15")
        self.assertEqual([preset["value"] for preset in presets], ["vl15", "v3"])
        self.assertFalse(
            next(item for item in presets if item["value"] == "v3")["defaults"]["enable_formula_recognition"]
        )

    def test_build_document_parse_options_keeps_force_ocr_enabled(self) -> None:
        options = build_document_parse_options(
            preset="v3",
            output_format="text",
            force_ocr=False,
            render_dpi=320,
            trim_margins=True,
        )

        self.assertEqual(options.preset, "v3")
        self.assertEqual(options.output_format, "text")
        self.assertTrue(options.force_ocr)
        self.assertEqual(options.render_dpi, 320)
        self.assertTrue(options.trim_margins)

    def test_legacy_formula_preset_is_normalized_to_v3(self) -> None:
        options = DocumentParseOptions.model_validate({"preset": "formula", "output_format": "markdown"})

        self.assertEqual(options.preset, "v3")
        self.assertTrue(options.enable_formula_recognition)
        self.assertEqual(options.render_dpi, 340)


if __name__ == "__main__":
    unittest.main()
