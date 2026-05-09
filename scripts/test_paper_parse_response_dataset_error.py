from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.schemas.papers import PaperParseResponse  # noqa: E402


class PaperParseResponseDatasetErrorTests(unittest.TestCase):
    def test_dataset_export_error_is_preserved(self) -> None:
        response = PaperParseResponse(
            paper_id=1,
            asset_id=2,
            parse_status="parsed",
            paper_status="parsed",
            question_count=3,
            section_count=1,
            tagged_count=0,
            warnings=["样本自动导入失败：disk full"],
            parse_options={"preset": "accurate"},
            dataset_sample_path=None,
            dataset_auto_exported=False,
            dataset_export_error="disk full",
        )

        payload = response.model_dump(mode="json")
        self.assertEqual(payload["dataset_export_error"], "disk full")
        self.assertFalse(payload["dataset_auto_exported"])


if __name__ == "__main__":
    unittest.main()
