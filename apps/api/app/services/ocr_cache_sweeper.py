from __future__ import annotations

import logging
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import Asset, LegacyLibraryFile
from library.pdf_ocr_pipeline import CHECKPOINT_NAMESPACE_FILENAME, _get_pdf_ocr_checkpoint_root


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class OCRCacheSweepResult:
    scanned_dirs: int = 0
    removed_dirs: int = 0
    kept_dirs: int = 0
    skipped_dirs: int = 0
    removed_paths: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class OCRCacheSweepService:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        settings = get_settings()
        if not settings.ocr_cache_sweep.enabled:
            logger.info("ocr_cache_sweep disabled")
            return
        if self._thread is not None and self._thread.is_alive():
            return
        interval_seconds = max(60, int(settings.ocr_cache_sweep.interval_seconds))
        self._thread = threading.Thread(
            target=self._run_loop,
            args=(interval_seconds, settings.ocr_cache_sweep.run_on_startup),
            name="ocr-cache-sweeper",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "ocr_cache_sweep started interval_seconds=%s run_on_startup=%s",
            interval_seconds,
            settings.ocr_cache_sweep.run_on_startup,
        )

    def stop(self, timeout_seconds: float = 5.0) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout_seconds)
        self._thread = None

    def run_once(self) -> OCRCacheSweepResult:
        checkpoint_root = _get_pdf_ocr_checkpoint_root()
        result = OCRCacheSweepResult()
        valid_sha256 = self._load_valid_pdf_asset_sha256()
        valid_namespaces = self._load_valid_asset_namespaces()

        for cache_dir in self._iter_checkpoint_leaf_dirs(checkpoint_root):
            result.scanned_dirs += 1
            fingerprint = self._read_marker(cache_dir / "source.sha256")
            namespace = self._read_marker(cache_dir / CHECKPOINT_NAMESPACE_FILENAME)
            should_keep = False
            if namespace:
                should_keep = namespace in valid_namespaces
            elif fingerprint:
                should_keep = fingerprint in valid_sha256
            else:
                result.warnings.append(f"missing markers: {cache_dir}")

            if should_keep:
                result.kept_dirs += 1
                continue

            try:
                shutil.rmtree(cache_dir, ignore_errors=True)
                result.removed_dirs += 1
                result.removed_paths.append(str(cache_dir))
            except Exception as exc:
                result.skipped_dirs += 1
                result.warnings.append(f"remove_failed {cache_dir}: {exc}")

        self._prune_empty_dirs(checkpoint_root)
        logger.info(
            "ocr_cache_sweep scanned_dirs=%s kept_dirs=%s removed_dirs=%s skipped_dirs=%s warnings=%s",
            result.scanned_dirs,
            result.kept_dirs,
            result.removed_dirs,
            result.skipped_dirs,
            len(result.warnings),
        )
        for removed_path in result.removed_paths:
            logger.info("ocr_cache_sweep removed_dir=%s", removed_path)
        for warning in result.warnings:
            logger.warning("ocr_cache_sweep warning=%s", warning)
        return result

    def _run_loop(self, interval_seconds: int, run_on_startup: bool) -> None:
        if run_on_startup:
            self._safe_run_once()
        while not self._stop_event.wait(interval_seconds):
            self._safe_run_once()

    def _safe_run_once(self) -> None:
        try:
            self.run_once()
        except Exception:
            logger.exception("ocr_cache_sweep failed")

    def _load_valid_pdf_asset_sha256(self) -> set[str]:
        with SessionLocal() as session:
            asset_rows = session.scalars(
                select(Asset).where((Asset.mime_type == "application/pdf") | (Asset.filename.like("%.pdf")))
            ).all()
            library_rows = session.scalars(
                select(LegacyLibraryFile).where((LegacyLibraryFile.mime == "application/pdf") | (LegacyLibraryFile.filename.like("%.pdf")))
            ).all()
        valid_sha256 = {str(asset.sha256).strip() for asset in asset_rows if asset.sha256}
        valid_sha256.update(str(file.sha256).strip() for file in library_rows if file.sha256)
        return valid_sha256

    def _load_valid_asset_namespaces(self) -> set[str]:
        with SessionLocal() as session:
            asset_ids = session.scalars(
                select(Asset.id).where((Asset.mime_type == "application/pdf") | (Asset.filename.like("%.pdf")))
            ).all()
        return {f"paper_asset_{int(asset_id)}" for asset_id in asset_ids}

    def _iter_checkpoint_leaf_dirs(self, checkpoint_root: Path) -> list[Path]:
        if not checkpoint_root.exists():
            return []
        return sorted(
            path for path in checkpoint_root.rglob("*") if path.is_dir() and any(path.glob("page_*.json"))
        )

    def _read_marker(self, path: Path) -> str:
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _prune_empty_dirs(self, checkpoint_root: Path) -> None:
        if not checkpoint_root.exists():
            return
        for path in sorted(checkpoint_root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if not path.is_dir():
                continue
            try:
                next(path.iterdir())
            except StopIteration:
                path.rmdir()
            except OSError:
                continue


ocr_cache_sweep_service = OCRCacheSweepService()
