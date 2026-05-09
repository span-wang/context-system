from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.paper_dataset import load_paper_dataset_sync_source  # noqa: E402


class PaperDatasetSyncSourceTests(unittest.TestCase):
    def test_prefers_labeled_gold_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir)
            sample_dir = output_root / "paper_000001_sample"
            sample_dir.mkdir(parents=True, exist_ok=True)
            (sample_dir / "meta.json").write_text("{}", encoding="utf-8")
            (sample_dir / "prediction.json").write_text(
                json.dumps({"sections": [{"title": "预测", "section_type": "single_choice", "questions": []}]}),
                encoding="utf-8",
            )
            (sample_dir / "gold.json").write_text(
                json.dumps({"label_status": "done", "sections": [{"title": "标注", "section_type": "single_choice", "questions": []}]}),
                encoding="utf-8",
            )

            source = load_paper_dataset_sync_source(1, "sample", output_root=output_root)
            self.assertTrue(source.used_gold)
            self.assertEqual(source.source_file, "gold.json")
            self.assertEqual(source.label_status, "done")

    def test_falls_back_to_prediction_when_gold_is_still_draft(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir)
            sample_dir = output_root / "paper_000002_sample"
            sample_dir.mkdir(parents=True, exist_ok=True)
            (sample_dir / "meta.json").write_text("{}", encoding="utf-8")
            (sample_dir / "prediction.json").write_text(
                json.dumps({"sections": [{"title": "预测", "section_type": "single_choice", "questions": [{"question_no": "1"}]}]}),
                encoding="utf-8",
            )
            (sample_dir / "gold.json").write_text(
                json.dumps({"label_status": "draft", "sections": [{"title": "标注", "section_type": "single_choice", "questions": [{"question_no": "9"}]}]}),
                encoding="utf-8",
            )

            source = load_paper_dataset_sync_source(2, "sample", output_root=output_root)
            self.assertFalse(source.used_gold)
            self.assertEqual(source.source_file, "prediction.json")
            self.assertEqual(source.label_status, "draft")


if __name__ == "__main__":
    unittest.main()
