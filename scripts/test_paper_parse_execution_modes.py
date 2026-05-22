from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.db.base import Base  # noqa: E402
from app.job_recovery import _sync_paper_parse_job_status  # noqa: E402
from app.models import AnalysisJob, Asset, ExamPaper, Subject, Tenant, User  # noqa: E402
from app.services.paper_ai_cleanup import PaperAICleanupResult  # noqa: E402
from app.services.papers import PaperService  # noqa: E402
from library.parse_options import DocumentParseOptions  # noqa: E402
from library.parser import ParsedDocument  # noqa: E402


class PaperParseExecutionModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.storage_root = Path(self.temp_dir.name)
        self.original_storage_root = os.environ.get("STORAGE_ROOT")
        os.environ["STORAGE_ROOT"] = str(self.storage_root)
        self._clear_settings_cache()

        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.session: Session = self.SessionLocal()

        tenant = Tenant(code="default", name="Default")
        self.session.add(tenant)
        self.session.flush()
        self.tenant = tenant

        subject = Subject(
            tenant_id=tenant.id,
            code="subject",
            name="Subject",
            created_by=None,
            updated_by=None,
        )
        self.session.add(subject)

        user = User(
            tenant_id=tenant.id,
            username="admin",
            password_hash="hash",
            display_name="Admin",
            created_by=None,
            updated_by=None,
        )
        self.session.add(user)
        self.session.flush()
        self.subject = subject
        self.user = user

        storage_rel_path = Path("papers/202605/mock-paper.txt")
        storage_path = self.storage_root / storage_rel_path
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_text("mock", encoding="utf-8")

        asset = Asset(
            tenant_id=tenant.id,
            subject_id=subject.id,
            asset_type="txt",
            source_type="exam",
            source_title="Paper",
            filename="mock-paper.txt",
            mime_type="text/plain",
            storage_path=str(storage_rel_path).replace("\\", "/"),
            sha256="sha-paper-parse-execution-modes",
            file_size=4,
            parse_status="pending",
            ocr_status="pending",
            created_by=user.id,
            updated_by=user.id,
        )
        self.session.add(asset)
        self.session.flush()
        self.asset = asset

        paper = ExamPaper(
            tenant_id=tenant.id,
            subject_id=subject.id,
            asset_id=asset.id,
            paper_name="Paper",
            status="uploaded",
            total_question_count=0,
            review_status="pending",
            created_by=user.id,
            updated_by=user.id,
        )
        self.session.add(paper)
        self.session.commit()
        self.paper = paper

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()
        if self.original_storage_root is None:
            os.environ.pop("STORAGE_ROOT", None)
        else:
            os.environ["STORAGE_ROOT"] = self.original_storage_root
        self._clear_settings_cache()
        self.temp_dir.cleanup()

    def test_ocr_only_mode_skips_ai_cleanup_and_marks_source_ready(self) -> None:
        cleanup_mock = MagicMock()

        with (
            patch("app.services.papers.parse_document", return_value=self._mock_parsed_document()),
            patch("app.services.papers.clean_and_structure_paper_source", cleanup_mock),
        ):
            response = PaperService(self.session).parse_paper(
                self.paper.id,
                options=DocumentParseOptions(preset="balanced"),
                execution_mode="ocr_only",
            )

        self.session.refresh(self.paper)
        self.session.refresh(self.asset)

        self.assertEqual(response.execution_mode, "ocr_only")
        self.assertGreater(response.token_count or 0, 0)
        self.assertEqual(self.paper.status, "source_ready")
        self.assertEqual(self.asset.parse_status, "source_ready")
        self.assertEqual(self.asset.ocr_status, "completed")
        self.assertIn("示例题干", self.asset.parsed_text or "")
        cleanup_mock.assert_not_called()

    def test_ai_cleanup_split_skips_async_standardize_submission(self) -> None:
        cleanup_result = PaperAICleanupResult(
            ai_source_text="1. 示例题干\nA. 选项甲\nB. 选项乙\n答案：A\n解析：示例解析",
            ai_sections=[
                {
                    "title": "单项选择题",
                    "section_type": "single_choice",
                    "sort_order": 1,
                    "questions": [],
                }
            ],
            ai_prediction={
                "sections": [
                    {
                        "title": "单项选择题",
                        "section_type": "single_choice",
                        "sort_order": 1,
                        "questions": [
                            {
                                "question_no": "1",
                                "node_role": "standalone",
                                "question_type": "single_choice",
                                "stem_text": "示例题干",
                                "options": ["A. 选项甲", "B. 选项乙"],
                                "answer_text": "A",
                                "analysis_text": "示例解析",
                                "source_raw_text": "1. 示例题干 A. 选项甲 B. 选项乙 答案：A 解析：示例解析",
                                "quality_score": 0.98,
                                "quality_issues": [],
                                "subquestion_count": 0,
                            }
                        ],
                    }
                ]
            },
            cleanup_report={"source": "ai_source.txt"},
        )
        start_jobs_mock = MagicMock(return_value=[SimpleNamespace(id=7, scope_config_json={"requested_count": 1})])

        class FakePaperReviewService:
            def __init__(self, session: Session) -> None:
                self.session = session

            def sync_questions_from_sections(self, *, paper_id: int, section_payloads: list[dict], operator_id: int | None, commit: bool) -> SimpleNamespace:
                return SimpleNamespace(imported_count=1)

        with (
            patch("app.services.papers.parse_document", return_value=self._mock_parsed_document()),
            patch("app.services.papers.clean_and_structure_paper_source", return_value=cleanup_result),
            patch("app.services.paper_review.PaperReviewService", FakePaperReviewService),
            patch("app.services.papers.should_auto_export_paper_dataset", return_value=False),
            patch("app.services.papers.start_paper_review_ai_standardize_jobs", start_jobs_mock),
        ):
            response = PaperService(self.session).parse_paper(
                self.paper.id,
                options=DocumentParseOptions(preset="balanced"),
                execution_mode="ai_cleanup_split",
            )

        self.session.refresh(self.paper)
        self.session.refresh(self.asset)

        start_jobs_mock.assert_not_called()
        self.assertEqual(response.execution_mode, "ai_cleanup_split")
        self.assertEqual(response.question_count, 1)
        self.assertEqual(response.ai_standardize_job_count, 0)
        self.assertEqual(self.paper.status, "parsed")
        self.assertEqual(self.asset.parse_status, "parsed")

    def test_job_recovery_preserves_ocr_only_completion_state(self) -> None:
        job = AnalysisJob(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            job_type="paper_parse",
            scope_type="paper",
            scope_config_json={"paper_id": self.paper.id, "execution_mode": "ocr_only"},
            status="completed",
            progress=100,
            result_summary_json={"paper_id": self.paper.id, "execution_mode": "ocr_only"},
            error_message=None,
            created_by=None,
            updated_by=None,
        )
        self.session.add(job)
        self.session.commit()

        changed = _sync_paper_parse_job_status(self.session, self.paper.id, job)

        self.assertTrue(changed)
        self.assertEqual(self.paper.status, "source_ready")
        self.assertEqual(self.asset.parse_status, "source_ready")
        self.assertEqual(self.asset.ocr_status, "completed")

    def _mock_parsed_document(self) -> ParsedDocument:
        text = "1. 示例题干\nA. 选项甲\nB. 选项乙\n答案：A\n解析：示例解析"
        return ParsedDocument(
            text=text,
            markdown=text,
            provider="mock/parser",
            used_ocr=True,
            raw_text=text,
            raw_markdown=text,
        )

    def _clear_settings_cache(self) -> None:
        for module_name, func_name in (
            ("app.core.config", "get_settings"),
            ("app.services.papers", "get_settings"),
            ("settings", "get_settings"),
        ):
            try:
                module = __import__(module_name, fromlist=[func_name])
                getattr(module, func_name).cache_clear()
            except Exception:
                continue


if __name__ == "__main__":
    unittest.main()
