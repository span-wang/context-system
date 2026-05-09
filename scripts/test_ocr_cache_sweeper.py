from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.db.base import Base  # noqa: E402
from app.models import Asset, LegacyLibraryFile, Subject, Tenant, User  # noqa: E402
from app.services import ocr_cache_sweeper as ocr_cache_sweeper_module  # noqa: E402
from app.services.ocr_cache_sweeper import OCRCacheSweepService  # noqa: E402


class OCRCacheSweeperTests(unittest.TestCase):
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
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.original_session_local = ocr_cache_sweeper_module.SessionLocal
        ocr_cache_sweeper_module.SessionLocal = self.SessionLocal
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
        self.user = User(
            tenant_id=self.tenant.id,
            username="admin",
            password_hash="hash",
            display_name="Admin",
            created_by=None,
            updated_by=None,
        )
        self.session.add_all([self.subject, self.user])
        self.session.flush()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()
        ocr_cache_sweeper_module.SessionLocal = self.original_session_local
        if self.original_storage_root is None:
            os.environ.pop("STORAGE_ROOT", None)
        else:
            os.environ["STORAGE_ROOT"] = self.original_storage_root
        try:
            from app.core.config import get_settings as get_app_settings

            get_app_settings.cache_clear()
        except Exception:
            pass
        self.temp_dir.cleanup()

    def test_run_once_removes_orphan_dirs_and_keeps_live_asset_and_library_dirs(self) -> None:
        asset = Asset(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            asset_type="pdf",
            source_type="exam",
            source_title="paper",
            filename="paper.pdf",
            mime_type="application/pdf",
            storage_path="papers/live.pdf",
            sha256="live-asset-sha",
            file_size=1,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        library_file = LegacyLibraryFile(
            id="lib-1",
            sha256="live-library-sha",
            filename="library.pdf",
            size=1,
            mime="application/pdf",
            storage_path="library/live.pdf",
            subject="Subject",
            category=None,
            chapter=None,
            source_type="book",
            source_authority="official",
            source_title="Library",
            source_publisher=None,
            source_code=None,
            source_version=None,
            year=None,
            tags="[]",
            parsed_text=None,
            token_count=None,
            created_at=self.tenant.created_at,
            last_used_at=None,
        )
        self.session.add_all([asset, library_file])
        self.session.commit()

        cache_root = self.storage_root / "cache" / "pdf_ocr_checkpoints"
        asset_dir = cache_root / "aa" / "asset-live"
        library_dir = cache_root / "bb" / "library-live"
        orphan_dir = cache_root / "cc" / "orphan"
        namespaced_orphan_dir = cache_root / "layout" / "dd" / "orphan-ns"
        for directory in (asset_dir, library_dir, orphan_dir, namespaced_orphan_dir):
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "page_00001.json").write_text("{}", encoding="utf-8")
        (asset_dir / "source.sha256").write_text("live-asset-sha", encoding="utf-8")
        (library_dir / "source.sha256").write_text("live-library-sha", encoding="utf-8")
        (orphan_dir / "source.sha256").write_text("orphan-sha", encoding="utf-8")
        (namespaced_orphan_dir / "cache.namespace").write_text("paper_asset_999999", encoding="utf-8")

        service = OCRCacheSweepService()
        result = service.run_once()

        self.assertEqual(result.scanned_dirs, 4)
        self.assertEqual(result.kept_dirs, 2)
        self.assertEqual(result.removed_dirs, 2)
        self.assertTrue(asset_dir.exists())
        self.assertTrue(library_dir.exists())
        self.assertFalse(orphan_dir.exists())
        self.assertFalse(namespaced_orphan_dir.exists())


if __name__ == "__main__":
    unittest.main()
