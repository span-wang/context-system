from __future__ import annotations

import os
import sys
import unittest
import asyncio
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import UploadFile
from starlette.datastructures import Headers
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.db.base import Base  # noqa: E402
from app.models import (  # noqa: E402
    AnalysisJob,
    Asset,
    ExamPaper,
    ExamQuestion,
    KnowledgePoint,
    PaperSection,
    QuestionBankItem,
    QuestionKnowledgeLink,
    QuestionSourceLink,
    ReviewTask,
    Subject,
    Tenant,
    User,
)
from app.services.papers import (  # noqa: E402
    PaperService,
    _build_pdf_layout_checkpoint_dir,
    _build_pdf_ocr_checkpoint_dir,
)
from app.repositories.papers import PaperRepository  # noqa: E402
from library.pdf_ocr_pipeline import CHECKPOINT_NAMESPACE_FILENAME, OCRPipelineOptions  # noqa: E402


class PaperDeleteCascadeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.storage_root = Path(self.temp_dir.name)
        self.original_storage_root = os.environ.get("STORAGE_ROOT")
        os.environ["STORAGE_ROOT"] = str(self.storage_root)
        try:
            from app.core.config import get_settings as get_app_settings

            get_app_settings.cache_clear()
        except Exception:
            pass
        try:
            from app.services.papers import get_settings as get_paper_service_settings

            get_paper_service_settings.cache_clear()
        except Exception:
            pass
        try:
            from settings import get_settings as get_project_settings

            get_project_settings.cache_clear()
        except Exception:
            pass
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.session: Session = self.SessionLocal()
        self.repository = PaperRepository(self.session)
        self.tenant = Tenant(code="default", name="Default")
        self.session.add(self.tenant)
        self.session.flush()
        self.subject = Subject(
            tenant_id=self.tenant.id,
            code="subject",
            name="Subject",
            created_by=None,
            updated_by=None,
        )
        self.session.add(self.subject)
        self.user = User(
            tenant_id=self.tenant.id,
            username="admin",
            password_hash="hash",
            display_name="Admin",
            created_by=None,
            updated_by=None,
        )
        self.session.add(self.user)
        self.session.flush()
        self.knowledge_point = KnowledgePoint(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            name="知识点",
            path="知识点",
            created_by=None,
            updated_by=None,
        )
        self.session.add(self.knowledge_point)
        self.session.flush()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()
        if self.original_storage_root is None:
            os.environ.pop("STORAGE_ROOT", None)
        else:
            os.environ["STORAGE_ROOT"] = self.original_storage_root
        try:
            from app.core.config import get_settings as get_app_settings

            get_app_settings.cache_clear()
        except Exception:
            pass
        try:
            from app.services.papers import get_settings as get_paper_service_settings

            get_paper_service_settings.cache_clear()
        except Exception:
            pass
        try:
            from settings import get_settings as get_project_settings

            get_project_settings.cache_clear()
        except Exception:
            pass
        self.temp_dir.cleanup()

    def test_delete_paper_removes_related_rows_and_bound_asset(self) -> None:
        asset = Asset(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            asset_type="pdf",
            source_type="exam",
            source_title="paper",
            filename="paper.pdf",
            mime_type="application/pdf",
            storage_path="papers/202605/paper.pdf",
            sha256="sha-paper-delete-test",
            file_size=1,
            parse_status="parsed",
            ocr_status="completed",
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add(asset)
        self.session.flush()
        asset_id = asset.id

        paper = ExamPaper(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            asset_id=asset.id,
            paper_name="Paper",
            status="parsed",
            total_question_count=1,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add(paper)
        self.session.flush()
        paper_id = paper.id

        section = PaperSection(
            tenant_id=self.tenant.id,
            paper_id=paper.id,
            section_name="单选",
            question_type="single_choice",
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add(section)
        self.session.flush()
        section_id = section.id

        question = ExamQuestion(
            tenant_id=self.tenant.id,
            paper_id=paper.id,
            subject_id=self.subject.id,
            section_id=section.id,
            question_no="1",
            question_uid="paper-delete-q1",
            question_type="single_choice",
            stem_text="题目",
            answer_text="A",
            analysis_text="解析",
            parse_status="parsed",
            review_status="approved",
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add(question)
        self.session.flush()
        question_id = question.id

        bank_item = QuestionBankItem(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            canonical_stem="题目",
            canonical_answer="A",
            canonical_analysis="解析",
            question_type="single_choice",
            source_count=1,
            status="published",
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add(bank_item)
        self.session.flush()

        self.session.add(
            QuestionSourceLink(
                tenant_id=self.tenant.id,
                bank_question_id=bank_item.id,
                exam_question_id=question.id,
                paper_id=paper.id,
                created_by=self.user.id,
                updated_by=self.user.id,
            )
        )
        self.session.add(
            QuestionKnowledgeLink(
                tenant_id=self.tenant.id,
                question_id=question.id,
                knowledge_point_id=self.knowledge_point.id,
                link_type="rule",
                created_by=self.user.id,
                updated_by=self.user.id,
            )
        )
        self.session.add(
            ReviewTask(
                tenant_id=self.tenant.id,
                task_type="review",
                target_type="question",
                target_id=str(question.id),
                created_by=self.user.id,
                updated_by=self.user.id,
            )
        )
        self.session.add(
            ReviewTask(
                tenant_id=self.tenant.id,
                task_type="review",
                target_type="paper",
                target_id=str(paper.id),
                created_by=self.user.id,
                updated_by=self.user.id,
            )
        )
        self.session.add(
            AnalysisJob(
                tenant_id=self.tenant.id,
                subject_id=self.subject.id,
                job_type="paper_parse",
                scope_type="paper",
                scope_config_json={"paper_id": paper.id},
                status="completed",
                progress=100,
                created_by=self.user.id,
                updated_by=self.user.id,
            )
        )
        self.session.add(
            AnalysisJob(
                tenant_id=self.tenant.id,
                subject_id=self.subject.id,
                job_type="paper_tagging",
                scope_type="paper",
                scope_config_json={"paper_id": paper.id},
                status="completed",
                progress=100,
                created_by=self.user.id,
                updated_by=self.user.id,
            )
        )
        self.session.commit()
        bank_item_id = bank_item.id

        self.repository.delete_paper(paper_id)
        self.session.commit()

        verify_session = self.SessionLocal()
        try:
            verify_repository = PaperRepository(verify_session)
            self.assertIsNone(verify_repository.get_paper(paper_id))
            self.assertIsNone(verify_repository.get_asset(asset_id))
            self.assertEqual(verify_repository.list_sections(paper_id), [])
            self.assertEqual(verify_repository.list_questions(paper_id), [])
            self.assertEqual(verify_repository.list_jobs(paper_id), [])
            self.assertEqual(verify_session.query(QuestionSourceLink).count(), 0)
            self.assertEqual(verify_session.query(QuestionKnowledgeLink).count(), 0)
            self.assertEqual(verify_session.query(ReviewTask).count(), 0)
            self.assertIsNone(verify_session.get(PaperSection, section_id))
            self.assertIsNone(verify_session.get(ExamQuestion, question_id))

            bank_item = verify_session.get(QuestionBankItem, bank_item_id)
            self.assertIsNotNone(bank_item)
            assert bank_item is not None
            self.assertEqual(bank_item.source_count, 0)
            self.assertEqual(bank_item.status, "draft")
        finally:
            verify_session.close()

    def test_delete_paper_keeps_shared_asset_when_other_paper_still_uses_it(self) -> None:
        asset = Asset(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            asset_type="pdf",
            source_type="exam",
            source_title="paper",
            filename="paper.pdf",
            mime_type="application/pdf",
            storage_path="papers/202605/paper.pdf",
            sha256="sha-shared-asset-delete-test",
            file_size=1,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add(asset)
        self.session.flush()

        first_paper = ExamPaper(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            asset_id=asset.id,
            paper_name="Paper A",
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        second_paper = ExamPaper(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            asset_id=asset.id,
            paper_name="Paper B",
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add_all([first_paper, second_paper])
        self.session.commit()

        first_paper_id = first_paper.id
        second_paper_id = second_paper.id
        asset_id = asset.id

        self.repository.delete_paper(first_paper_id)
        self.session.commit()

        verify_session = self.SessionLocal()
        try:
            verify_repository = PaperRepository(verify_session)
            self.assertIsNone(verify_repository.get_paper(first_paper_id))
            self.assertIsNotNone(verify_repository.get_paper(second_paper_id))
            self.assertIsNotNone(verify_repository.get_asset(asset_id))
        finally:
            verify_session.close()

    def test_delete_parse_outputs_removes_question_side_data_but_keeps_paper(self) -> None:
        asset = Asset(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            asset_type="pdf",
            source_type="exam",
            source_title="paper",
            filename="paper.pdf",
            mime_type="application/pdf",
            storage_path="papers/202605/paper.pdf",
            sha256="sha-delete-parse-outputs-test",
            file_size=1,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add(asset)
        self.session.flush()

        paper = ExamPaper(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            asset_id=asset.id,
            paper_name="Paper",
            status="parsed",
            total_question_count=1,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add(paper)
        self.session.flush()

        section = PaperSection(
            tenant_id=self.tenant.id,
            paper_id=paper.id,
            section_name="单选",
            question_type="single_choice",
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add(section)
        self.session.flush()

        question = ExamQuestion(
            tenant_id=self.tenant.id,
            paper_id=paper.id,
            subject_id=self.subject.id,
            section_id=section.id,
            question_no="1",
            question_uid="delete-parse-outputs-q1",
            question_type="single_choice",
            stem_text="题目",
            answer_text="A",
            analysis_text="解析",
            parse_status="parsed",
            review_status="approved",
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add(question)
        self.session.flush()

        bank_item = QuestionBankItem(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            canonical_stem="题目",
            canonical_answer="A",
            canonical_analysis="解析",
            question_type="single_choice",
            source_count=1,
            status="published",
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add(bank_item)
        self.session.flush()

        self.session.add(
            QuestionSourceLink(
                tenant_id=self.tenant.id,
                bank_question_id=bank_item.id,
                exam_question_id=question.id,
                paper_id=paper.id,
                created_by=self.user.id,
                updated_by=self.user.id,
            )
        )
        self.session.add(
            QuestionKnowledgeLink(
                tenant_id=self.tenant.id,
                question_id=question.id,
                knowledge_point_id=self.knowledge_point.id,
                link_type="rule",
                created_by=self.user.id,
                updated_by=self.user.id,
            )
        )
        self.session.add(
            ReviewTask(
                tenant_id=self.tenant.id,
                task_type="review",
                target_type="question",
                target_id=str(question.id),
                created_by=self.user.id,
                updated_by=self.user.id,
            )
        )
        self.session.commit()

        paper_id = paper.id
        asset_id = asset.id
        question_id = question.id
        section_id = section.id
        bank_item_id = bank_item.id

        self.repository.delete_parse_outputs(paper_id)
        self.session.commit()

        verify_session = self.SessionLocal()
        try:
            verify_repository = PaperRepository(verify_session)
            self.assertIsNotNone(verify_repository.get_paper(paper_id))
            self.assertIsNotNone(verify_repository.get_asset(asset_id))
            self.assertEqual(verify_repository.list_sections(paper_id), [])
            self.assertEqual(verify_repository.list_questions(paper_id), [])
            self.assertEqual(verify_session.query(QuestionSourceLink).count(), 0)
            self.assertEqual(verify_session.query(QuestionKnowledgeLink).count(), 0)
            self.assertEqual(verify_session.query(ReviewTask).count(), 0)
            self.assertIsNone(verify_session.get(PaperSection, section_id))
            self.assertIsNone(verify_session.get(ExamQuestion, question_id))

            bank_item = verify_session.get(QuestionBankItem, bank_item_id)
            self.assertIsNotNone(bank_item)
            assert bank_item is not None
            self.assertEqual(bank_item.source_count, 0)
            self.assertEqual(bank_item.status, "draft")
        finally:
            verify_session.close()

    def test_delete_paper_removes_storage_and_cache_files(self) -> None:
        sha256 = "sha-delete-storage-test"
        storage_dir = self.storage_root / "papers" / "202605"
        storage_dir.mkdir(parents=True, exist_ok=True)
        storage_path = storage_dir / f"{sha256}.pdf"
        storage_path.write_bytes(b"pdf")

        parsed_cache_root = self.storage_root / "cache" / "parsed"
        parsed_cache_root.mkdir(parents=True, exist_ok=True)
        for name in (
            f"{sha256}.txt",
            f"{sha256}.json",
        ):
            (parsed_cache_root / name).write_text("cache", encoding="utf-8")

        dataset_dir = self.storage_root / "paper_parser_dataset" / "paper_000001_Paper"
        dataset_dir.mkdir(parents=True, exist_ok=True)
        (dataset_dir / "source.txt").write_text("sample", encoding="utf-8")

        asset = Asset(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            asset_type="pdf",
            source_type="exam",
            source_title="paper",
            filename="paper.pdf",
            mime_type="application/pdf",
            storage_path="papers/202605/sha-delete-storage-test.pdf",
            sha256=sha256,
            file_size=1,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add(asset)
        self.session.flush()
        asset_cache_prefix = f"paper_asset_{asset.id}"
        checkpoint_root = self.storage_root / "cache" / "pdf_ocr_checkpoints"
        cache_options = OCRPipelineOptions(cache_namespace=asset_cache_prefix)
        ocr_cache_dir = _build_pdf_ocr_checkpoint_dir(
            checkpoint_root,
            sha256,
            cache_options,
            cache_namespace=asset_cache_prefix,
        )
        ocr_cache_dir.mkdir(parents=True, exist_ok=True)
        (ocr_cache_dir / "source.sha256").write_text(sha256, encoding="utf-8")
        (ocr_cache_dir / "page_00001.json").write_text("{}", encoding="utf-8")

        layout_cache_dir = _build_pdf_layout_checkpoint_dir(
            checkpoint_root,
            sha256,
            cache_options,
            cache_namespace=asset_cache_prefix,
        )
        layout_cache_dir.mkdir(parents=True, exist_ok=True)
        (layout_cache_dir / "source.sha256").write_text(sha256, encoding="utf-8")
        (layout_cache_dir / "page_00001.json").write_text("{}", encoding="utf-8")
        for name in (
            f"{asset_cache_prefix}__default.txt",
            f"{asset_cache_prefix}__default.json",
        ):
            (parsed_cache_root / name).write_text("cache", encoding="utf-8")

        service = PaperService(self.session)
        paper = ExamPaper(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            asset_id=asset.id,
            paper_name="Paper",
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add(paper)
        self.session.commit()

        original_cleanup = service._cleanup_deleted_asset_files

        def strict_cleanup(*args, **kwargs):
            return original_cleanup(*args, **kwargs)

        service._cleanup_deleted_asset_files = strict_cleanup  # type: ignore[method-assign]
        try:
            service.delete_paper(paper.id)
        except Exception as exc:
            self.fail(f"delete_paper raised unexpectedly: {exc}")

        self.assertFalse(storage_path.exists())
        self.assertFalse((parsed_cache_root / f"{asset_cache_prefix}__default.txt").exists())
        self.assertFalse((parsed_cache_root / f"{asset_cache_prefix}__default.json").exists())
        self.assertFalse((parsed_cache_root / f"{sha256}.txt").exists())
        self.assertFalse((parsed_cache_root / f"{sha256}.json").exists())
        self.assertFalse((ocr_cache_dir / "page_00001.json").exists())
        self.assertFalse((ocr_cache_dir / "source.sha256").exists())
        self.assertFalse((layout_cache_dir / "page_00001.json").exists())
        self.assertFalse((layout_cache_dir / "source.sha256").exists())
        self.assertFalse(dataset_dir.exists())
        self.assertFalse((checkpoint_root / ocr_cache_dir.parent.name).exists())
        self.assertFalse((checkpoint_root / "layout" / layout_cache_dir.parent.name).exists())
        self.assertFalse(checkpoint_root.exists())

    def test_delete_paper_keeps_sha_cache_when_duplicate_asset_still_exists(self) -> None:
        sha256 = "sha-duplicate-cache-keep-test"
        parsed_cache_root = self.storage_root / "cache" / "parsed"
        parsed_cache_root.mkdir(parents=True, exist_ok=True)
        ocr_cache_dir = self.storage_root / "cache" / "pdf_ocr_checkpoints" / "aa" / "aa-cache"
        ocr_cache_dir.mkdir(parents=True, exist_ok=True)
        (ocr_cache_dir / "source.sha256").write_text(sha256, encoding="utf-8")
        (ocr_cache_dir / "page_00001.json").write_text("{}", encoding="utf-8")

        first_storage = self.storage_root / "papers" / "202605" / "dup-a.pdf"
        second_storage = self.storage_root / "papers" / "202605" / "dup-b.pdf"
        first_storage.parent.mkdir(parents=True, exist_ok=True)
        first_storage.write_bytes(b"a")
        second_storage.write_bytes(b"b")

        first_asset = Asset(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            asset_type="pdf",
            source_type="exam",
            source_title="paper-a",
            filename="paper-a.pdf",
            mime_type="application/pdf",
            storage_path="papers/202605/dup-a.pdf",
            sha256=sha256,
            file_size=1,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        second_asset = Asset(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            asset_type="pdf",
            source_type="exam",
            source_title="paper-b",
            filename="paper-b.pdf",
            mime_type="application/pdf",
            storage_path="papers/202605/dup-b.pdf",
            sha256=sha256,
            file_size=1,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add_all([first_asset, second_asset])
        self.session.flush()
        first_asset_cache_prefix = f"paper_asset_{first_asset.id}"
        second_asset_cache_prefix = f"paper_asset_{second_asset.id}"
        for name in (
            f"{first_asset_cache_prefix}__default.txt",
            f"{first_asset_cache_prefix}__default.json",
            f"{second_asset_cache_prefix}__default.txt",
            f"{second_asset_cache_prefix}__default.json",
            f"{sha256}.txt",
            f"{sha256}.json",
        ):
            (parsed_cache_root / name).write_text("cache", encoding="utf-8")

        first_paper = ExamPaper(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            asset_id=first_asset.id,
            paper_name="Paper A",
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        second_paper = ExamPaper(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            asset_id=second_asset.id,
            paper_name="Paper B",
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add_all([first_paper, second_paper])
        self.session.commit()

        service = PaperService(self.session)
        service.delete_paper(first_paper.id)

        self.assertFalse(first_storage.exists())
        self.assertTrue(second_storage.exists())
        self.assertFalse((parsed_cache_root / f"{first_asset_cache_prefix}__default.txt").exists())
        self.assertFalse((parsed_cache_root / f"{first_asset_cache_prefix}__default.json").exists())
        self.assertTrue((parsed_cache_root / f"{second_asset_cache_prefix}__default.txt").exists())
        self.assertTrue((parsed_cache_root / f"{second_asset_cache_prefix}__default.json").exists())
        self.assertTrue((parsed_cache_root / f"{sha256}.txt").exists())
        self.assertTrue((parsed_cache_root / f"{sha256}.json").exists())
        self.assertTrue(ocr_cache_dir.exists())

    def test_delete_paper_removes_auto_fallback_cache_when_duplicate_asset_still_exists(self) -> None:
        sha256 = "sha-duplicate-auto-fallback-cache-test"
        checkpoint_root = self.storage_root / "cache" / "pdf_ocr_checkpoints"

        first_storage = self.storage_root / "papers" / "202605" / "fallback-a.pdf"
        second_storage = self.storage_root / "papers" / "202605" / "fallback-b.pdf"
        first_storage.parent.mkdir(parents=True, exist_ok=True)
        first_storage.write_bytes(b"a")
        second_storage.write_bytes(b"b")

        first_asset = Asset(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            asset_type="pdf",
            source_type="exam",
            source_title="paper-a",
            filename="paper-a.pdf",
            mime_type="application/pdf",
            storage_path="papers/202605/fallback-a.pdf",
            sha256=sha256,
            file_size=1,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        second_asset = Asset(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            asset_type="pdf",
            source_type="exam",
            source_title="paper-b",
            filename="paper-b.pdf",
            mime_type="application/pdf",
            storage_path="papers/202605/fallback-b.pdf",
            sha256=sha256,
            file_size=1,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add_all([first_asset, second_asset])
        self.session.flush()

        first_asset_cache_prefix = f"paper_asset_{first_asset.id}"
        second_asset_cache_prefix = f"paper_asset_{second_asset.id}"
        fallback_options_first = OCRPipelineOptions(
            force_ocr=True,
            render_dpi=240,
            cache_namespace=first_asset_cache_prefix,
            trim_margins=True,
            remove_repeated_lines=True,
            watermark_detection=False,
        )
        fallback_options_second = OCRPipelineOptions(
            force_ocr=True,
            render_dpi=240,
            cache_namespace=second_asset_cache_prefix,
            trim_margins=True,
            remove_repeated_lines=True,
            watermark_detection=False,
        )
        first_asset_cache_dir = _build_pdf_ocr_checkpoint_dir(
            checkpoint_root,
            sha256,
            fallback_options_first,
            cache_namespace=first_asset_cache_prefix,
        )
        first_asset_cache_dir.mkdir(parents=True, exist_ok=True)
        (first_asset_cache_dir / "source.sha256").write_text(sha256, encoding="utf-8")
        (first_asset_cache_dir / "page_00001.json").write_text("{}", encoding="utf-8")

        second_asset_cache_dir = _build_pdf_ocr_checkpoint_dir(
            checkpoint_root,
            sha256,
            fallback_options_second,
            cache_namespace=second_asset_cache_prefix,
        )
        second_asset_cache_dir.mkdir(parents=True, exist_ok=True)
        (second_asset_cache_dir / "source.sha256").write_text(sha256, encoding="utf-8")
        (second_asset_cache_dir / "page_00001.json").write_text("{}", encoding="utf-8")

        first_paper = ExamPaper(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            asset_id=first_asset.id,
            paper_name="Paper A",
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        second_paper = ExamPaper(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            asset_id=second_asset.id,
            paper_name="Paper B",
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add_all([first_paper, second_paper])
        self.session.commit()

        service = PaperService(self.session)
        service.delete_paper(first_paper.id)

        self.assertFalse(first_storage.exists())
        self.assertTrue(second_storage.exists())
        self.assertFalse(first_asset_cache_dir.exists())
        self.assertTrue(second_asset_cache_dir.exists())

    def test_delete_paper_removes_namespace_marked_cache_when_duplicate_asset_still_exists(self) -> None:
        sha256 = "sha-duplicate-namespace-marker-cache-test"
        checkpoint_root = self.storage_root / "cache" / "pdf_ocr_checkpoints"

        first_storage = self.storage_root / "papers" / "202605" / "marker-a.pdf"
        second_storage = self.storage_root / "papers" / "202605" / "marker-b.pdf"
        first_storage.parent.mkdir(parents=True, exist_ok=True)
        first_storage.write_bytes(b"a")
        second_storage.write_bytes(b"b")

        first_asset = Asset(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            asset_type="pdf",
            source_type="exam",
            source_title="paper-a",
            filename="paper-a.pdf",
            mime_type="application/pdf",
            storage_path="papers/202605/marker-a.pdf",
            sha256=sha256,
            file_size=1,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        second_asset = Asset(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            asset_type="pdf",
            source_type="exam",
            source_title="paper-b",
            filename="paper-b.pdf",
            mime_type="application/pdf",
            storage_path="papers/202605/marker-b.pdf",
            sha256=sha256,
            file_size=1,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add_all([first_asset, second_asset])
        self.session.flush()

        first_asset_cache_prefix = f"paper_asset_{first_asset.id}"
        second_asset_cache_prefix = f"paper_asset_{second_asset.id}"
        first_asset_cache_dir = checkpoint_root / "custom" / "first-asset-cache"
        second_asset_cache_dir = checkpoint_root / "custom" / "second-asset-cache"
        first_asset_cache_dir.mkdir(parents=True, exist_ok=True)
        second_asset_cache_dir.mkdir(parents=True, exist_ok=True)
        (first_asset_cache_dir / "source.sha256").write_text(sha256, encoding="utf-8")
        (second_asset_cache_dir / "source.sha256").write_text(sha256, encoding="utf-8")
        (first_asset_cache_dir / CHECKPOINT_NAMESPACE_FILENAME).write_text(first_asset_cache_prefix, encoding="utf-8")
        (second_asset_cache_dir / CHECKPOINT_NAMESPACE_FILENAME).write_text(second_asset_cache_prefix, encoding="utf-8")
        (first_asset_cache_dir / "page_00001.json").write_text("{}", encoding="utf-8")
        (second_asset_cache_dir / "page_00001.json").write_text("{}", encoding="utf-8")

        first_paper = ExamPaper(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            asset_id=first_asset.id,
            paper_name="Paper A",
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        second_paper = ExamPaper(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            asset_id=second_asset.id,
            paper_name="Paper B",
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add_all([first_paper, second_paper])
        self.session.commit()

        service = PaperService(self.session)
        service.delete_paper(first_paper.id)

        self.assertFalse(first_storage.exists())
        self.assertTrue(second_storage.exists())
        self.assertFalse(first_asset_cache_dir.exists())
        self.assertTrue(second_asset_cache_dir.exists())

    def test_upload_same_file_twice_creates_independent_assets_and_papers(self) -> None:
        service = PaperService(self.session)
        payload = b"same file bytes for paper upload"

        async def upload_once(name: str):
            upload = UploadFile(
                file=BytesIO(payload),
                filename="same.pdf",
                size=len(payload),
                headers=Headers({"content-type": "application/pdf"}),
            )
            return await service.upload_paper(
                file=upload,
                paper_name=name,
                subject_id=self.subject.id,
            )

        first = asyncio.run(upload_once("Paper First"))
        second = asyncio.run(upload_once("Paper Second"))

        self.assertNotEqual(first.id, second.id)
        self.assertNotEqual(first.asset_id, second.asset_id)
        self.assertEqual(first.sha256, second.sha256)

        first_paper = self.repository.get_paper(first.id)
        second_paper = self.repository.get_paper(second.id)
        self.assertIsNotNone(first_paper)
        self.assertIsNotNone(second_paper)
        assert first_paper is not None
        assert second_paper is not None
        self.assertNotEqual(first_paper.asset_id, second_paper.asset_id)

        first_asset = self.repository.get_asset(first.asset_id)
        second_asset = self.repository.get_asset(second.asset_id)
        self.assertIsNotNone(first_asset)
        self.assertIsNotNone(second_asset)
        assert first_asset is not None
        assert second_asset is not None
        self.assertEqual(first_asset.sha256, second_asset.sha256)
        self.assertNotEqual(first_asset.storage_path, second_asset.storage_path)
        self.assertTrue((self.storage_root / first_asset.storage_path).exists())
        self.assertTrue((self.storage_root / second_asset.storage_path).exists())


if __name__ == "__main__":
    unittest.main()
