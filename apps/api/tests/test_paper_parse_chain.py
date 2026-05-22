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

from fastapi import HTTPException

import app.services.paper_parse_jobs as paper_parse_jobs_module
import app.services.papers as papers_module
from app.models import AnalysisJob, Asset, ExamPaper
from library.parse_options import DocumentParseOptions
from library.parser import ParsedDocument


class _RepositoryStub:
    def __init__(self, paper: ExamPaper, asset: Asset) -> None:
        self._paper = paper
        self._asset = asset

    def get_paper(self, paper_id: int) -> ExamPaper | None:
        return self._paper if paper_id == self._paper.id else None

    def get_asset(self, asset_id: int | None) -> Asset | None:
        return self._asset if asset_id == self._asset.id else None


class _SessionStub:
    def __init__(self, job: AnalysisJob | None = None) -> None:
        self.job = job
        self.added: list[AnalysisJob] = []
        self.deleted: list[AnalysisJob] = []
        self.committed = False

    def add(self, job: AnalysisJob) -> None:
        job.id = 999
        self.added.append(job)

    def delete(self, job: AnalysisJob) -> None:
        self.deleted.append(job)

    def commit(self) -> None:
        self.committed = True

    def refresh(self, job: AnalysisJob) -> None:
        return None

    def flush(self) -> None:
        return None


class PaperParseChainTests(unittest.TestCase):
    def test_ai_cleanup_split_reuses_latest_preview_snapshot_instead_of_reparsing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            original_settings = papers_module.get_settings
            original_parse_document = papers_module.parse_document
            original_clean_and_structure = papers_module.clean_and_structure_paper_source
            original_cancel_jobs = papers_module.cancel_active_paper_review_ai_standardize_jobs
            original_should_export = papers_module.should_auto_export_paper_dataset
            original_start_standardize = papers_module.start_paper_review_ai_standardize_jobs
            papers_module.get_settings = lambda: SimpleNamespace(storage=SimpleNamespace(root_path=tmp_path), app=SimpleNamespace(default_tenant_code="default"))
            try:
                paper = ExamPaper(id=11, tenant_id=1, asset_id=22, paper_name="测试卷", status="source_ready", total_question_count=0, parsed_version=1, review_status="pending")
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
                    parse_status="source_ready",
                    ocr_status="completed",
                )
                parsed = ParsedDocument(
                    text="VL15 清洗后正文",
                    markdown="VL15 清洗后正文",
                    provider="paddleocr_vl_1_5/local",
                    used_ocr=True,
                    raw_text="VL15 原始正文",
                    raw_markdown="VL15 原始正文",
                    warnings=["parse_preset=vl15"],
                )
                preview_options = DocumentParseOptions(preset="vl15", output_format="markdown", render_dpi=240, pdf_page_chunk_size=4)
                papers_module._write_paper_parse_preview_cache(
                    paper=paper,
                    asset=asset,
                    parsed_document=parsed,
                    options=preview_options,
                    execution_mode="ocr_only",
                    parse_runtime={
                        "provider": parsed.provider,
                        "execution_mode": "ocr_only",
                        "options": preview_options.resolved_summary(),
                    },
                )

                service = papers_module.PaperService(session=object())
                service.repository = _RepositoryStub(paper, asset)
                service.session = SimpleNamespace(commit=lambda: None)
                service._sync_parse_runtime_status = lambda *_args, **_kwargs: None

                parse_called = False

                def fail_parse_document(*_args, **_kwargs):
                    nonlocal parse_called
                    parse_called = True
                    raise AssertionError("ai_cleanup_split should reuse cached preview instead of reparsing")

                captured_cleanup_sources: list[str] = []

                def fake_clean_and_structure(source_text: str, **_kwargs):
                    captured_cleanup_sources.append(source_text)
                    return SimpleNamespace(
                        ai_source_text=source_text,
                        ai_sections=[{"title": "单选题", "section_type": "single_choice", "questions": [{"question_no": "1", "node_role": "standalone", "question_type": "single_choice", "stem_text": "题干", "options": ["A. 选项"], "answer_text": "", "analysis_text": "", "subquestion_count": 0, "quality_score": 0.0, "quality_issues": [], "source_raw_text": "1. 题干\nA. 选项"}]}],
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
                        debug_payload={},
                        warnings=[],
                        cleanup_report={"source": "ai_source.txt"},
                    )

                papers_module.parse_document = fail_parse_document
                papers_module.clean_and_structure_paper_source = fake_clean_and_structure
                papers_module.cancel_active_paper_review_ai_standardize_jobs = lambda *args, **kwargs: None
                papers_module.should_auto_export_paper_dataset = lambda: False
                papers_module.start_paper_review_ai_standardize_jobs = lambda *args, **kwargs: []
                service.repository.get_default_tenant = lambda _code: SimpleNamespace(id=1)
                service.repository.get_default_user = lambda _tenant_id: SimpleNamespace(id=1)
                service.repository.get_subject = lambda _subject_id: None
                service.repository.get_subject_category = lambda _category_id: None
                service.repository.list_knowledge_points = lambda _subject_id=None: [SimpleNamespace(subject_id=1)]
                service.repository.delete_parse_outputs = lambda _paper_id: None
                service.repository.create_section = lambda section: SimpleNamespace(id=101, start_no=1, end_no=1, question_type=section.question_type)
                service.repository.list_sections = lambda _paper_id: []

                result = service.parse_paper(
                    paper.id,
                    options=DocumentParseOptions(preset="v3", output_format="markdown", render_dpi=320),
                    execution_mode="ai_cleanup_split",
                )

                self.assertFalse(parse_called)
                self.assertEqual(captured_cleanup_sources, ["VL15 原始正文"])
                self.assertEqual(result.provider, "paddleocr_vl_1_5/local")
                self.assertEqual(result.parse_options["preset"], "vl15")
                self.assertTrue(result.parse_runtime.get("source_reused_from_cache"))
                self.assertEqual(result.parse_runtime.get("source_execution_mode"), "ocr_only")
            finally:
                papers_module.get_settings = original_settings
                papers_module.parse_document = original_parse_document
                papers_module.clean_and_structure_paper_source = original_clean_and_structure
                papers_module.cancel_active_paper_review_ai_standardize_jobs = original_cancel_jobs
                papers_module.should_auto_export_paper_dataset = original_should_export
                papers_module.start_paper_review_ai_standardize_jobs = original_start_standardize

    def test_start_parse_job_rejects_active_job_with_different_parse_options(self) -> None:
        original_service = paper_parse_jobs_module.PaperService
        original_find_active = paper_parse_jobs_module._find_active_paper_parse_job
        original_default_tenant_id = paper_parse_jobs_module._default_tenant_id
        try:
            paper = SimpleNamespace(id=11, subject_id=1)
            session = _SessionStub()
            active_job = AnalysisJob(
                id=123,
                tenant_id=1,
                subject_id=1,
                job_type="paper_parse",
                scope_type="paper",
                scope_config_json={
                    "paper_id": 11,
                    "execution_mode": "ocr_only",
                    "parse_options": {"preset": "v3", "output_format": "markdown", "force_ocr": True},
                },
                status="running",
                progress=50,
            )

            class _ServiceStub:
                def __init__(self, _session) -> None:
                    self.repository = SimpleNamespace(get_paper=lambda paper_id: paper if paper_id == 11 else None)

            paper_parse_jobs_module.PaperService = _ServiceStub
            paper_parse_jobs_module._find_active_paper_parse_job = lambda _session, _paper_id: active_job
            paper_parse_jobs_module._default_tenant_id = lambda _session: 1

            with self.assertRaises(HTTPException) as ctx:
                paper_parse_jobs_module.start_paper_parse_job(
                    session,
                    11,
                    DocumentParseOptions(preset="vl15", output_format="markdown", render_dpi=240),
                    execution_mode="ocr_only",
                )

            self.assertEqual(ctx.exception.status_code, 409)
            self.assertIn("解析参数不同", str(ctx.exception.detail))
        finally:
            paper_parse_jobs_module.PaperService = original_service
            paper_parse_jobs_module._find_active_paper_parse_job = original_find_active
            paper_parse_jobs_module._default_tenant_id = original_default_tenant_id

    def test_start_parse_job_deletes_previous_completed_paper_parse_jobs(self) -> None:
        original_service = paper_parse_jobs_module.PaperService
        original_find_active = paper_parse_jobs_module._find_active_paper_parse_job
        original_default_tenant_id = paper_parse_jobs_module._default_tenant_id
        original_thread = paper_parse_jobs_module.threading.Thread
        try:
            previous_job = AnalysisJob(
                id=120,
                tenant_id=1,
                subject_id=1,
                job_type="paper_parse",
                scope_type="paper",
                scope_config_json={"paper_id": 11, "execution_mode": "ocr_only", "parse_options": {"preset": "v3"}},
                status="completed",
                progress=100,
            )
            session = _SessionStub()
            paper = SimpleNamespace(id=11, subject_id=1)

            class _RepositoryStub:
                def get_paper(self, paper_id: int):
                    return paper if paper_id == 11 else None

                def list_jobs(self, paper_id: int, job_type: str | None = None):
                    if paper_id == 11 and job_type == "paper_parse":
                        return [previous_job]
                    return []

            class _ServiceStub:
                def __init__(self, _session) -> None:
                    self.repository = _RepositoryStub()

            class _ThreadStub:
                def __init__(self, *args, **kwargs) -> None:
                    return None

                def start(self) -> None:
                    return None

            paper_parse_jobs_module.PaperService = _ServiceStub
            paper_parse_jobs_module._find_active_paper_parse_job = lambda _session, _paper_id: None
            paper_parse_jobs_module._default_tenant_id = lambda _session: 1
            paper_parse_jobs_module.threading.Thread = _ThreadStub

            job = paper_parse_jobs_module.start_paper_parse_job(
                session,
                11,
                DocumentParseOptions(preset="vl15", output_format="markdown", render_dpi=240),
                execution_mode="ocr_only",
            )

            self.assertEqual(job.id, 999)
            self.assertEqual([item.id for item in session.deleted], [120])
            self.assertEqual(len(session.added), 1)
        finally:
            paper_parse_jobs_module.PaperService = original_service
            paper_parse_jobs_module._find_active_paper_parse_job = original_find_active
            paper_parse_jobs_module._default_tenant_id = original_default_tenant_id
            paper_parse_jobs_module.threading.Thread = original_thread


if __name__ == "__main__":
    unittest.main()
