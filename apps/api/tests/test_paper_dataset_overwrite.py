from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.paper_dataset import export_paper_parser_sample


class PaperDatasetOverwriteTests(unittest.TestCase):
    def test_export_sample_removes_older_dirs_for_same_paper_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            old_dir = root / "paper_000011_old_name"
            old_dir.mkdir(parents=True, exist_ok=True)
            (old_dir / "meta.json").write_text("{}", encoding="utf-8")

            sample_dir = export_paper_parser_sample(
                paper_id=11,
                paper_name="新试卷名",
                source_text="原文",
                ai_source_text="清洗后原文",
                ai_prediction={
                    "version": 2,
                    "source_format": "ai_structured_question_groups",
                    "section_count": 1,
                    "question_count": 1,
                    "sections": [
                        {
                            "title": "单选题",
                            "section_type": "single_choice",
                            "sort_order": 1,
                            "question_count": 1,
                            "questions": [
                                {
                                    "order": 1,
                                    "question_no": "1",
                                    "node_role": "standalone",
                                    "question_type": "single_choice",
                                    "stem_text": "题干",
                                    "options": ["A. 选项"],
                                    "answer_text": "",
                                    "analysis_text": "",
                                    "subquestion_count": 0,
                                    "quality_score": 0.0,
                                    "quality_issues": [],
                                    "source_raw_text": "1. 题干\nA. 选项",
                                    "subquestions": [],
                                }
                            ],
                        }
                    ],
                },
                output_root=root,
                init_gold=False,
                include_source=False,
            )

            self.assertTrue(sample_dir.exists())
            self.assertFalse(old_dir.exists())
            self.assertEqual(
                sorted(path.name for path in root.glob("paper_000011_*") if path.is_dir()),
                [sample_dir.name],
            )


if __name__ == "__main__":
    unittest.main()
