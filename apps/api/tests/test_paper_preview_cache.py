from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

import app.services.papers as papers_module
from app.models import Asset, ExamPaper
from library.parse_options import DocumentParseOptions
from library.parser import ParsedDocument


class PaperPreviewCacheTests(unittest.TestCase):
    def test_preview_cache_round_trip_uses_saved_formal_parse_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            original_settings = papers_module.get_settings
            papers_module.get_settings = lambda: SimpleNamespace(storage=SimpleNamespace(root_path=tmp_path))
            try:
                paper = ExamPaper(id=11, tenant_id=1, paper_name="测试卷", status="parsed", total_question_count=0, parsed_version=1, review_status="pending")
                asset = Asset(
                    id=22,
                    tenant_id=1,
                    asset_type="pdf",
                    source_type="exam",
                    source_title="测试卷",
                    filename="sample.pdf",
                    mime_type="application/pdf",
                    storage_path="papers/sample.pdf",
                    sha256="abc",
                    file_size=123,
                    parse_status="parsed",
                    ocr_status="completed",
                )
                parsed = ParsedDocument(
                    text="清洗后正文",
                    markdown="清洗后正文",
                    provider="pdf_ocr_pipeline/paddleocr",
                    used_ocr=True,
                    warnings=["cached warning"],
                    cleanup_report={"removed_lines": 2},
                    cleanup_score=8.6,
                    raw_text="原始 OCR 正文",
                    raw_markdown="原始 OCR 正文",
                )
                options = DocumentParseOptions(preset="v3", output_format="markdown", render_dpi=320, pdf_page_chunk_size=4)
                parse_runtime = {
                    "provider": parsed.provider,
                    "execution_mode": "full_chain",
                    "options": options.resolved_summary(),
                    "model_settings": {"engine": "paddleocr", "device": "gpu"},
                }

                papers_module._write_paper_parse_preview_cache(
                    paper=paper,
                    asset=asset,
                    parsed_document=parsed,
                    options=options,
                    execution_mode="full_chain",
                    parse_runtime=parse_runtime,
                )

                preview = papers_module._read_paper_parse_preview_cache(paper=paper, asset=asset)

                self.assertIsNotNone(preview)
                assert preview is not None
                self.assertEqual(preview.paper_id, 11)
                self.assertEqual(preview.asset_id, 22)
                self.assertEqual(preview.provider, "pdf_ocr_pipeline/paddleocr")
                self.assertEqual(preview.raw_text, "原始 OCR 正文")
                self.assertEqual(preview.content, "清洗后正文")
                self.assertEqual(preview.parse_options["preset"], "v3")
                self.assertEqual(preview.parse_runtime["model_settings"]["device"], "gpu")
                self.assertEqual(preview.execution_mode, "full_chain")
                self.assertTrue(preview.cached_at)
            finally:
                papers_module.get_settings = original_settings

    def test_parse_runtime_snapshot_includes_model_settings(self) -> None:
        original_get_ocr_settings = papers_module._get_paddle_ocr_settings
        papers_module._get_paddle_ocr_settings = lambda: {
            "ocr_version": "PP-OCRv5",
            "text_detection_model_name": "PP-OCRv5_server_det",
            "text_recognition_model_name": "PP-OCRv5_server_rec",
            "text_detection_model_dir": None,
            "text_recognition_model_dir": None,
            "use_textline_orientation": True,
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "device": "gpu:0",
        }
        try:
            runtime = papers_module._build_parse_runtime_snapshot(
                DocumentParseOptions(preset="v3", output_format="markdown"),
                provider="pp_structure_v3",
                execution_mode="full_chain",
            )
        finally:
            papers_module._get_paddle_ocr_settings = original_get_ocr_settings

        self.assertEqual(runtime["provider"], "pp_structure_v3")
        self.assertEqual(runtime["execution_mode"], "full_chain")
        self.assertEqual(runtime["options"]["preset"], "v3")
        self.assertEqual(runtime["model_settings"]["engine"], "paddleocr")
        self.assertEqual(runtime["model_settings"]["text_detection_model_name"], "PP-OCRv5_server_det")
        self.assertEqual(runtime["model_settings"]["device"], "gpu:0")


if __name__ == "__main__":
    unittest.main()
