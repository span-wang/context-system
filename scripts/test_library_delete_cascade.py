from __future__ import annotations

import asyncio
import os
import sys
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.db.base import Base  # noqa: E402
from app.models import Asset, ExamPaper, ExamQuestion, LegacyLibraryFile, PaperSection, Subject, Tenant, User  # noqa: E402
from app.services.papers import PaperService  # noqa: E402
from app.core.config import get_settings as get_app_settings  # noqa: E402
from library.service import LibraryService  # noqa: E402
import library.service as library_service_module  # noqa: E402
from schemas.library import LibraryFile  # noqa: E402
from storage.local import LocalFSStorage  # noqa: E402


class _FakeDatabase:
    def __init__(self, file: LibraryFile) -> None:
        self.file = file
        self.deleted_ids: list[str] = []

    def delete_library_file(self, file_id: str) -> LibraryFile | None:
        if file_id != self.file.id:
            return None
        self.deleted_ids.append(file_id)
        return self.file


class LibraryDeleteCascadeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.storage_root = Path(self.temp_dir.name)
        self.original_storage_root = os.environ.get("STORAGE_ROOT")
        os.environ["STORAGE_ROOT"] = str(self.storage_root)
        try:
            get_app_settings.cache_clear()
        except Exception:
            pass
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.original_library_session_local = library_service_module.SessionLocal
        library_service_module.SessionLocal = self.SessionLocal
        self.session: Session = self.SessionLocal()
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

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()
        library_service_module.SessionLocal = self.original_library_session_local
        if self.original_storage_root is None:
            os.environ.pop("STORAGE_ROOT", None)
        else:
            os.environ["STORAGE_ROOT"] = self.original_storage_root
        try:
            get_app_settings.cache_clear()
        except Exception:
            pass
        self.temp_dir.cleanup()

    def test_delete_library_file_removes_bound_exam_paper_and_questions(self) -> None:
        sha256 = "library-delete-bound-paper-sha"
        paper_rel = Path("papers/202605/bound-paper.pdf")
        library_rel = Path("library/202605/bound-paper.pdf")
        paper_path = self.storage_root / paper_rel
        library_path = self.storage_root / library_rel
        paper_path.parent.mkdir(parents=True, exist_ok=True)
        library_path.parent.mkdir(parents=True, exist_ok=True)
        paper_path.write_bytes(b"paper")
        library_path.write_bytes(b"library")

        asset = Asset(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            asset_type="pdf",
            source_type="exam",
            source_title="paper",
            filename="paper.pdf",
            mime_type="application/pdf",
            storage_path=paper_rel.as_posix(),
            sha256=sha256,
            file_size=5,
            parse_status="parsed",
            ocr_status="completed",
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
            question_uid="library-delete-q1",
            question_type="single_choice",
            stem_text="题目",
            answer_text="A",
            analysis_text="解析",
            parse_status="parsed",
            review_status="pending",
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add(question)
        self.session.commit()
        paper_id = paper.id
        asset_id = asset.id

        file = LibraryFile(
            id="lib-file-1",
            sha256=sha256,
            filename="paper.pdf",
            size=5,
            mime="application/pdf",
            storage_path=library_rel.as_posix(),
            subject="Subject",
            category=None,
            chapter=None,
            source_type="exam",
            source_authority="medium",
            source_title="paper",
            source_publisher=None,
            source_code=None,
            source_version=None,
            year=None,
            tags=[],
            token_count=None,
            created_at=datetime.utcnow(),
            last_used_at=None,
        )
        fake_db = _FakeDatabase(file)
        service = LibraryService(fake_db, LocalFSStorage(self.storage_root))

        asyncio.run(service.delete_file(file.id))

        verify = self.SessionLocal()
        try:
            self.assertIsNone(verify.get(ExamPaper, paper_id))
            self.assertIsNone(verify.get(Asset, asset_id))
            self.assertEqual(verify.scalar(select(PaperSection).where(PaperSection.paper_id == paper_id)), None)
            self.assertEqual(verify.scalar(select(ExamQuestion).where(ExamQuestion.paper_id == paper_id)), None)
        finally:
            verify.close()

        self.assertFalse(paper_path.exists())
        self.assertFalse(library_path.exists())
        self.assertEqual(fake_db.deleted_ids, [file.id])


if __name__ == "__main__":
    unittest.main()
