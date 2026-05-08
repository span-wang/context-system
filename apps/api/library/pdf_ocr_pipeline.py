from __future__ import annotations

import gc
import io
import hashlib
import json
import math
import os
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any

from settings import PROJECT_ROOT


NOISE_TEXT_PATTERN = re.compile(r"\S+")
WATERMARK_ALPHA_THRESHOLD = 245
DEFAULT_RENDER_DPI = 240
DEFAULT_PADDLE_OCR_VERSION = "PP-OCRv5"
DEFAULT_PADDLE_OCR_DETECTION_MODEL = "PP-OCRv5_server_det"
DEFAULT_PADDLE_OCR_RECOGNITION_MODEL = "PP-OCRv5_server_rec"
PADDLE_OCR_LOCK = RLock()
DEFAULT_OCR_ENGINE = "paddle"
DEFAULT_PDF_PARSE_PAGE_BATCH_SIZE = 4
OCR_ENGINE_ENV = "PDF_OCR_ENGINE"
PDF_PARSE_PAGE_BATCH_SIZE_ENV = "PDF_PARSE_PAGE_CHUNK_SIZE"
PDF_OCR_CHECKPOINT_DIR_ENV = "PDF_OCR_CHECKPOINT_DIR"
PADDLE_OCR_VERSION_ENV = "PDF_OCR_VERSION"
PADDLE_OCR_DETECTION_MODEL_ENV = "PDF_OCR_DETECTION_MODEL"
PADDLE_OCR_RECOGNITION_MODEL_ENV = "PDF_OCR_RECOGNITION_MODEL"
PADDLE_OCR_DETECTION_MODEL_DIR_ENV = "PDF_OCR_DETECTION_MODEL_DIR"
PADDLE_OCR_RECOGNITION_MODEL_DIR_ENV = "PDF_OCR_RECOGNITION_MODEL_DIR"
PADDLE_OCR_TEXTLINE_ORIENTATION_ENV = "PDF_OCR_USE_TEXTLINE_ORIENTATION"
PADDLE_OCR_DOC_ORIENTATION_ENV = "PDF_OCR_USE_DOC_ORIENTATION"
PADDLE_OCR_DOC_UNWARPING_ENV = "PDF_OCR_USE_DOC_UNWARPING"
PADDLE_OCR_DEVICE_ENV = "PDF_OCR_DEVICE"
OCRProgressCallback = Callable[[int, int, dict[str, object] | None], None]


@dataclass
class OCRPipelineOptions:
    force_ocr: bool = False
    render_dpi: int = DEFAULT_RENDER_DPI
    max_pages: int | None = None
    crop_header_ratio: float = 0.0
    crop_footer_ratio: float = 0.0
    trim_margins: bool = True
    remove_repeated_lines: bool = True
    repeated_line_min_pages: int = 2
    watermark_detection: bool = True
    watermark_brightness_threshold: int = WATERMARK_ALPHA_THRESHOLD
    enable_formula_recognition: bool = False
    formula_confidence_threshold: float = 0.5
    page_chunk_size: int | None = None


@dataclass
class OCRTextBlock:
    page_number: int
    block_id: str
    text: str
    bbox: list[float] = field(default_factory=list)
    score: float | None = None
    block_type: str = "text"
    latex: str | None = None
    removed_as_noise: bool = False


@dataclass
class OCRPageResult:
    page_number: int
    width: float
    height: float
    text: str
    markdown: str
    blocks: list[OCRTextBlock] = field(default_factory=list)
    headers_removed: list[str] = field(default_factory=list)
    footers_removed: list[str] = field(default_factory=list)
    repeated_noise_removed: list[str] = field(default_factory=list)
    formulas: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class OCRDocumentResult:
    filename: str
    provider: str
    used_ocr: bool
    text: str
    markdown: str
    pages: list[OCRPageResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_pdf_ocr_pipeline(
    pdf_bytes: bytes,
    filename: str,
    options: OCRPipelineOptions | None = None,
    progress_callback: OCRProgressCallback | None = None,
) -> OCRDocumentResult:
    with PADDLE_OCR_LOCK:
        try:
            return _run_pdf_ocr_pipeline(
                pdf_bytes,
                filename,
                options=options,
                progress_callback=progress_callback,
            )
        finally:
            release_paddle_ocr_resources()


def _run_pdf_ocr_pipeline(
    pdf_bytes: bytes,
    filename: str,
    options: OCRPipelineOptions | None = None,
    progress_callback: OCRProgressCallback | None = None,
) -> OCRDocumentResult:
    options = options or OCRPipelineOptions()

    if not options.force_ocr and _looks_like_text_pdf(pdf_bytes):
        direct = _extract_pdf_text(pdf_bytes, filename)
        if direct is not None and _has_meaningful_text(direct.text):
            return direct

    try:
        total_page_count = _get_pdf_page_count(pdf_bytes)
    except Exception as exc:
        return OCRDocumentResult(
            filename=filename,
            provider="pdf_ocr_pipeline",
            used_ocr=False,
            text="",
            markdown="",
            warnings=[f"Unable to render PDF pages: {exc}"],
            metadata={"filename": filename},
        )

    target_page_count = min(total_page_count, options.max_pages) if options.max_pages is not None else total_page_count
    if target_page_count <= 0:
        return OCRDocumentResult(
            filename=filename,
            provider="pdf_ocr_pipeline",
            used_ocr=False,
            text="",
            markdown="",
            warnings=["PDF contains no renderable pages."],
            metadata={"filename": filename},
        )

    document_warnings: list[str] = []
    page_batch_size = _get_pdf_page_batch_size(options)
    checkpoint_dir = _get_pdf_ocr_checkpoint_dir(
        pdf_bytes,
        options,
        _get_pdf_ocr_checkpoint_root(),
    )
    cached_pages_by_number = {
        page_number: cached_page
        for page_number in range(1, target_page_count + 1)
        if (cached_page := _load_pdf_ocr_checkpoint_page(checkpoint_dir, page_number)) is not None
    }
    total_chunks = _count_pdf_chunks(target_page_count, page_batch_size)
    resumed_pages = len(cached_pages_by_number)
    resumed_chunks = _count_completed_chunks(cached_pages_by_number.keys(), page_batch_size)
    resume_start_page = _first_missing_page(cached_pages_by_number, target_page_count)
    if options.max_pages is not None and total_page_count > target_page_count:
        document_warnings.append(f"OCR limited to first {target_page_count} of {total_page_count} pages.")

    if len(cached_pages_by_number) == target_page_count:
        page_results = [cached_pages_by_number[page_number] for page_number in range(1, target_page_count + 1)]
        document_warnings.append(f"OCR resumed from {len(cached_pages_by_number)} cached pages.")
        if progress_callback is not None:
            progress_callback(
                target_page_count,
                target_page_count,
                {
                    "done_pages": target_page_count,
                    "total_pages": target_page_count,
                    "page_batch_size": page_batch_size,
                    "chunk_count": total_chunks,
                    "completed_chunk_count": total_chunks,
                    "resumed_pages": resumed_pages,
                    "resumed_chunk_count": resumed_chunks,
                    "resume_start_page": resume_start_page,
                },
            )
        if options.remove_repeated_lines:
            _remove_repeated_noise(page_results, options.repeated_line_min_pages)
        full_text = "\n\n".join(page.text for page in page_results if page.text.strip())
        full_markdown = "\n\n".join(page.markdown for page in page_results if page.markdown.strip())
        return OCRDocumentResult(
            filename=filename,
            provider="pdf_ocr_pipeline/checkpoint",
            used_ocr=True,
            text=full_text,
            markdown=full_markdown or full_text,
            pages=page_results,
            warnings=document_warnings,
            metadata={
                "filename": filename,
                "page_count": len(page_results),
                "total_page_count": total_page_count,
                "target_page_count": target_page_count,
                "page_batch_size": page_batch_size,
                "checkpoint_dir": str(checkpoint_dir),
                "chunk_count": total_chunks,
                "completed_chunk_count": total_chunks,
                "resumed_pages": resumed_pages,
                "resumed_chunk_count": resumed_chunks,
                "resume_start_page": resume_start_page,
                "options": asdict(options),
            },
        )

    ocr_engine, ocr_engine_name, engine_warning = _get_ocr_engine()
    if ocr_engine is None:
        return OCRDocumentResult(
            filename=filename,
            provider="pdf_ocr_pipeline",
            used_ocr=False,
            text="",
            markdown="",
            warnings=[engine_warning or "No OCR engine is installed or failed to initialize."],
            metadata={"filename": filename, "total_page_count": total_page_count},
        )

    formula_engine, formula_warning = _get_formula_engine(options.enable_formula_recognition)

    page_results: list[OCRPageResult] = []
    if cached_pages_by_number:
        document_warnings.append(f"OCR resumed from {len(cached_pages_by_number)} cached pages.")
    if engine_warning:
        document_warnings.append(engine_warning)
    if formula_warning:
        document_warnings.append(formula_warning)

    pending_start_page: int | None = None
    for page_number in range(1, target_page_count + 1):
        cached_page = cached_pages_by_number.get(page_number)
        if cached_page is not None:
            if pending_start_page is not None:
                _process_pdf_ocr_page_range(
                    pdf_bytes,
                    options,
                    ocr_engine=ocr_engine,
                    ocr_engine_name=ocr_engine_name,
                    formula_engine=formula_engine,
                    page_results=page_results,
                    document_warnings=document_warnings,
                    progress_callback=progress_callback,
                    target_page_count=target_page_count,
                    page_batch_size=page_batch_size,
                    checkpoint_dir=checkpoint_dir,
                    total_chunks=total_chunks,
                    resumed_pages=resumed_pages,
                    resumed_chunks=resumed_chunks,
                    resume_start_page=resume_start_page,
                    start_page=pending_start_page,
                    end_page=page_number - 1,
                )
                pending_start_page = None
            page_results.append(cached_page)
            if progress_callback is not None:
                progress_callback(
                    page_number,
                    target_page_count,
                    {
                        "done_pages": len(page_results),
                        "total_pages": target_page_count,
                        "page_batch_size": page_batch_size,
                        "chunk_count": total_chunks,
                        "completed_chunk_count": _count_fully_completed_chunks(
                            len(page_results),
                            target_page_count,
                            page_batch_size,
                        ),
                        "resumed_pages": resumed_pages,
                        "resumed_chunk_count": resumed_chunks,
                        "resume_start_page": resume_start_page,
                    },
                )
            continue

        if pending_start_page is None:
            pending_start_page = page_number

    if pending_start_page is not None:
        _process_pdf_ocr_page_range(
            pdf_bytes,
            options,
            ocr_engine=ocr_engine,
            ocr_engine_name=ocr_engine_name,
            formula_engine=formula_engine,
            page_results=page_results,
            document_warnings=document_warnings,
            progress_callback=progress_callback,
            target_page_count=target_page_count,
            page_batch_size=page_batch_size,
            checkpoint_dir=checkpoint_dir,
            total_chunks=total_chunks,
            resumed_pages=resumed_pages,
            resumed_chunks=resumed_chunks,
            resume_start_page=resume_start_page,
            start_page=pending_start_page,
            end_page=target_page_count,
        )

    page_results.sort(key=lambda page: page.page_number)

    if not page_results:
        return OCRDocumentResult(
            filename=filename,
            provider="pdf_ocr_pipeline",
            used_ocr=True,
            text="",
            markdown="",
            warnings=document_warnings or ["PDF OCR produced no page results."],
            metadata={
                "filename": filename,
                "page_count": 0,
                "total_page_count": total_page_count,
                "target_page_count": target_page_count,
                "page_batch_size": page_batch_size,
                "chunk_count": total_chunks,
                "completed_chunk_count": 0,
                "options": asdict(options),
            },
        )

    if options.remove_repeated_lines:
        _remove_repeated_noise(page_results, options.repeated_line_min_pages)

    full_text = "\n\n".join(page.text for page in page_results if page.text.strip())
    full_markdown = "\n\n".join(page.markdown for page in page_results if page.markdown.strip())
    return OCRDocumentResult(
        filename=filename,
        provider=f"pdf_ocr_pipeline/{ocr_engine_name}",
        used_ocr=True,
        text=full_text,
        markdown=full_markdown or full_text,
        pages=page_results,
        warnings=document_warnings,
        metadata={
            "filename": filename,
            "page_count": len(page_results),
            "total_page_count": total_page_count,
            "target_page_count": target_page_count,
            "page_batch_size": page_batch_size,
            "checkpoint_dir": str(checkpoint_dir),
            "chunk_count": total_chunks,
            "completed_chunk_count": total_chunks,
            "resumed_pages": resumed_pages,
            "resumed_chunk_count": resumed_chunks,
            "resume_start_page": resume_start_page,
            "options": asdict(options),
            "ocr_settings": _get_paddle_ocr_settings() if ocr_engine_name == "paddleocr" else {},
        },
    )


def load_pipeline_options(raw: str | None) -> OCRPipelineOptions:
    if not raw:
        return OCRPipelineOptions()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        try:
            import yaml

            data = yaml.safe_load(raw)
        except Exception as exc:
            raise ValueError(f"Invalid pipeline options JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Pipeline options must be a JSON object.")
    return OCRPipelineOptions(**data)


def write_pipeline_outputs(result: OCRDocumentResult, output_dir: str | Path) -> dict[str, Path]:
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    stem = Path(result.filename).stem or "document"
    json_path = output_root / f"{stem}.ocr.json"
    markdown_path = output_root / f"{stem}.ocr.md"
    text_path = output_root / f"{stem}.ocr.txt"
    json_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(result.markdown, encoding="utf-8")
    text_path.write_text(result.text, encoding="utf-8")
    return {
        "json": json_path,
        "markdown": markdown_path,
        "text": text_path,
    }


def _looks_like_text_pdf(pdf_bytes: bytes) -> bool:
    head = pdf_bytes[:4096]
    return b"/Font" in head or b"/Contents" in head or b"/Type /Page" in head


def _extract_pdf_text(pdf_bytes: bytes, filename: str) -> OCRDocumentResult | None:
    try:
        import pymupdf
    except Exception:
        try:
            import fitz as pymupdf
        except Exception:
            return None

    try:
        document = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return None

    pages: list[OCRPageResult] = []
    parts: list[str] = []
    try:
        for page_number, page in enumerate(document, start=1):
            text = page.get_text("text").strip()
            parts.append(text)
            pages.append(
                OCRPageResult(
                    page_number=page_number,
                    width=float(page.rect.width),
                    height=float(page.rect.height),
                    text=text,
                    markdown=text,
                )
            )
    finally:
        document.close()

    merged = "\n\n".join(part for part in parts if part)
    return OCRDocumentResult(
        filename=filename,
        provider="pymupdf_text",
        used_ocr=False,
        text=merged,
        markdown=merged,
        pages=pages,
        metadata={"filename": filename, "page_count": len(pages)},
    )


def _has_meaningful_text(text: str) -> bool:
    return len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text or "")) >= 24


def _get_pdf_page_count(pdf_bytes: bytes) -> int:
    try:
        import pymupdf
    except Exception:
        import fitz as pymupdf

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        return int(doc.page_count)
    finally:
        doc.close()


def _render_pdf_pages(pdf_bytes: bytes, dpi: int, max_pages: int | None = None) -> tuple[list[dict[str, Any]], int]:
    total_page_count = _get_pdf_page_count(pdf_bytes)
    target_page_count = min(total_page_count, max_pages) if max_pages is not None else total_page_count
    pages = _render_pdf_page_range(pdf_bytes, dpi, 0, target_page_count)
    return pages, total_page_count


def _render_pdf_page_range(
    pdf_bytes: bytes,
    dpi: int,
    start_page_index: int,
    end_page_index: int,
) -> list[dict[str, Any]]:
    try:
        import pymupdf
    except Exception:
        import fitz as pymupdf

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    pages: list[dict[str, Any]] = []
    try:
        scale = dpi / 72.0
        matrix = pymupdf.Matrix(scale, scale)
        safe_start = max(0, start_page_index)
        safe_end = min(max(safe_start, end_page_index), doc.page_count)
        for page_index in range(safe_start, safe_end):
            page = doc.load_page(page_index)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            image_bytes = pix.tobytes("png")
            pages.append(
                {
                    "page_number": page_index + 1,
                    "width": float(page.rect.width),
                    "height": float(page.rect.height),
                    "image_bytes": image_bytes,
                }
            )
    finally:
        doc.close()
    return pages


def _render_pdf_page_range_resilient(
    pdf_bytes: bytes,
    dpi: int,
    start_page_index: int,
    end_page_index: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        return _render_pdf_page_range(pdf_bytes, dpi, start_page_index, end_page_index), []
    except Exception as exc:
        if end_page_index - start_page_index <= 1:
            return [], [f"Unable to render PDF page {start_page_index + 1}: {exc}"]

        mid_page_index = start_page_index + max(1, (end_page_index - start_page_index) // 2)
        left_pages, left_warnings = _render_pdf_page_range_resilient(
            pdf_bytes,
            dpi,
            start_page_index,
            mid_page_index,
        )
        right_pages, right_warnings = _render_pdf_page_range_resilient(
            pdf_bytes,
            dpi,
            mid_page_index,
            end_page_index,
        )
        warning = (
            f"PDF render batch pages {start_page_index + 1}-{end_page_index} failed; "
            f"retried with smaller page chunks: {exc}"
        )
        return [*left_pages, *right_pages], [warning, *left_warnings, *right_warnings]


def _get_pdf_page_batch_size(options: OCRPipelineOptions) -> int:
    if options.page_chunk_size is not None:
        return max(1, min(50, int(options.page_chunk_size)))
    raw_value = os.getenv(PDF_PARSE_PAGE_BATCH_SIZE_ENV)
    if raw_value:
        try:
            return max(1, min(50, int(raw_value)))
        except ValueError:
            return DEFAULT_PDF_PARSE_PAGE_BATCH_SIZE
    if options.enable_formula_recognition or options.render_dpi >= 260:
        return 2
    if options.render_dpi <= 170:
        return 8
    return DEFAULT_PDF_PARSE_PAGE_BATCH_SIZE


def _process_pdf_ocr_page_range(
    pdf_bytes: bytes,
    options: OCRPipelineOptions,
    *,
    ocr_engine: Any,
    ocr_engine_name: str,
    formula_engine: Any,
    page_results: list[OCRPageResult],
    document_warnings: list[str],
    progress_callback: OCRProgressCallback | None,
    target_page_count: int,
    page_batch_size: int,
    checkpoint_dir: Path,
    total_chunks: int,
    resumed_pages: int,
    resumed_chunks: int,
    resume_start_page: int | None,
    start_page: int,
    end_page: int,
) -> None:
    for batch_start in range(start_page - 1, end_page, page_batch_size):
        batch_end = min(batch_start + page_batch_size, end_page)
        pages, render_warnings = _render_pdf_page_range_resilient(
            pdf_bytes,
            options.render_dpi,
            batch_start,
            batch_end,
        )
        document_warnings.extend(render_warnings)

        for page in pages:
            page_number = int(page.get("page_number") or 0)
            page_result = _ocr_single_page(
                page=page,
                page_number=page_number,
                ocr_engine=ocr_engine,
                ocr_engine_name=ocr_engine_name,
                formula_engine=formula_engine,
                options=options,
            )
            page_results.append(page_result)
            _save_pdf_ocr_checkpoint_page(checkpoint_dir, page_result)
            if progress_callback is not None:
                progress_callback(
                    page_number,
                    target_page_count,
                    {
                        "done_pages": len(page_results),
                        "total_pages": target_page_count,
                        "page_batch_size": page_batch_size,
                        "chunk_count": total_chunks,
                        "completed_chunk_count": _count_fully_completed_chunks(
                            len(page_results),
                            target_page_count,
                            page_batch_size,
                        ),
                        "current_chunk_index": (batch_start // page_batch_size) + 1,
                        "current_chunk_page_from": batch_start + 1,
                        "current_chunk_page_to": batch_end,
                        "resumed_pages": resumed_pages,
                        "resumed_chunk_count": resumed_chunks,
                        "resume_start_page": resume_start_page,
                    },
                )

        release_paddle_ocr_resources(clear_cached_engines=False, force_clear_cache=True)


def _get_pdf_ocr_checkpoint_root() -> Path:
    raw = os.getenv(PDF_OCR_CHECKPOINT_DIR_ENV)
    if raw and raw.strip():
        root = Path(raw.strip())
    else:
        try:
            from settings import get_settings

            root = get_settings().storage.root_path / "cache" / "pdf_ocr_checkpoints"
        except Exception:
            root = PROJECT_ROOT / "data" / "cache" / "pdf_ocr_checkpoints"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _get_pdf_ocr_checkpoint_dir(
    pdf_bytes: bytes,
    options: OCRPipelineOptions,
    root: Path,
) -> Path:
    options_payload = {
        key: value
        for key, value in asdict(options).items()
        if key not in {"max_pages", "page_chunk_size"}
    }
    payload = json.dumps(
        {
            "sha256": hashlib.sha256(pdf_bytes).hexdigest(),
            "options": options_payload,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    checkpoint_dir = root / digest[:2] / digest
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    return checkpoint_dir


def _load_pdf_ocr_checkpoint_page(checkpoint_dir: Path, page_number: int) -> OCRPageResult | None:
    path = checkpoint_dir / f"page_{page_number:05d}.json"
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    return _ocr_page_result_from_dict(raw)


def _save_pdf_ocr_checkpoint_page(checkpoint_dir: Path, page_result: OCRPageResult) -> None:
    if not _should_persist_pdf_ocr_page(page_result):
        return
    path = checkpoint_dir / f"page_{page_result.page_number:05d}.json"
    tmp_path = path.with_suffix(".json.tmp")
    payload = json.dumps(_ocr_page_result_to_dict(page_result), ensure_ascii=False, indent=2)
    tmp_path.write_text(payload, encoding="utf-8")
    tmp_path.replace(path)


def _should_persist_pdf_ocr_page(page_result: OCRPageResult) -> bool:
    transient_prefixes = (
        "OCR prediction failed:",
        "PIL is not installed",
        "numpy is unavailable",
    )
    return not any((warning or "").startswith(transient_prefixes) for warning in page_result.warnings)


def _ocr_page_result_to_dict(page_result: OCRPageResult) -> dict[str, Any]:
    payload = asdict(page_result)
    return payload


def _ocr_page_result_from_dict(raw: dict[str, Any]) -> OCRPageResult:
    blocks: list[OCRTextBlock] = []
    for item in raw.get("blocks") or []:
        if not isinstance(item, dict):
            continue
        blocks.append(
            OCRTextBlock(
                page_number=int(item.get("page_number") or raw.get("page_number") or 0),
                block_id=str(item.get("block_id") or ""),
                text=str(item.get("text") or ""),
                bbox=[float(value) for value in item.get("bbox") or [] if isinstance(value, (int, float))],
                score=_safe_float(item.get("score")),
                block_type=str(item.get("block_type") or "text"),
                latex=item.get("latex") if item.get("latex") is None else str(item.get("latex") or ""),
                removed_as_noise=bool(item.get("removed_as_noise")),
            )
        )
    return OCRPageResult(
        page_number=int(raw.get("page_number") or 0),
        width=float(raw.get("width") or 0.0),
        height=float(raw.get("height") or 0.0),
        text=str(raw.get("text") or ""),
        markdown=str(raw.get("markdown") or ""),
        blocks=blocks,
        headers_removed=[str(item) for item in raw.get("headers_removed") or [] if str(item).strip()],
        footers_removed=[str(item) for item in raw.get("footers_removed") or [] if str(item).strip()],
        repeated_noise_removed=[str(item) for item in raw.get("repeated_noise_removed") or [] if str(item).strip()],
        formulas=[str(item) for item in raw.get("formulas") or [] if str(item).strip()],
        warnings=[str(item) for item in raw.get("warnings") or [] if str(item).strip()],
    )


def _count_pdf_chunks(total_pages: int, page_batch_size: int) -> int:
    if total_pages <= 0:
        return 0
    return ((total_pages - 1) // max(1, page_batch_size)) + 1


def _count_completed_chunks(page_numbers: Any, page_batch_size: int) -> int:
    return len(
        {
            ((int(page_number) - 1) // max(1, page_batch_size)) + 1
            for page_number in page_numbers
            if int(page_number) > 0
        }
    )


def _count_fully_completed_chunks(done_pages: int, total_pages: int, page_batch_size: int) -> int:
    if done_pages <= 0:
        return 0
    if done_pages >= total_pages:
        return _count_pdf_chunks(total_pages, page_batch_size)
    return done_pages // max(1, page_batch_size)


def _first_missing_page(cached_pages_by_number: dict[int, OCRPageResult], target_page_count: int) -> int | None:
    for page_number in range(1, target_page_count + 1):
        if page_number not in cached_pages_by_number:
            return page_number
    return None


def _get_paddle_ocr_engine():
    try:
        from paddleocr import PaddleOCR
    except Exception:
        return None

    _get_paddle_ocr_engine._touched = True
    settings = _get_paddle_ocr_settings()
    if getattr(_get_paddle_ocr_engine, "_engine", None) is None:
        with PADDLE_OCR_LOCK:
            if getattr(_get_paddle_ocr_engine, "_engine", None) is None:
                try:
                    init_kwargs = {
                        "use_doc_orientation_classify": settings["use_doc_orientation_classify"],
                        "use_doc_unwarping": settings["use_doc_unwarping"],
                        "use_textline_orientation": settings["use_textline_orientation"],
                        "text_rec_score_thresh": 0.0,
                    }
                    if settings["text_detection_model_dir"]:
                        init_kwargs["text_detection_model_dir"] = settings["text_detection_model_dir"]
                    else:
                        init_kwargs["text_detection_model_name"] = settings["text_detection_model_name"]
                    if settings["text_recognition_model_dir"]:
                        init_kwargs["text_recognition_model_dir"] = settings["text_recognition_model_dir"]
                    else:
                        init_kwargs["text_recognition_model_name"] = settings["text_recognition_model_name"]
                    if (
                        not settings["text_detection_model_name"]
                        and not settings["text_recognition_model_name"]
                        and not settings["text_detection_model_dir"]
                        and not settings["text_recognition_model_dir"]
                    ):
                        init_kwargs["lang"] = "ch"
                        init_kwargs["ocr_version"] = settings["ocr_version"]
                    _get_paddle_ocr_engine._engine = PaddleOCR(**init_kwargs)
                except Exception:
                    return None
    return _get_paddle_ocr_engine._engine


def _get_paddle_ocr_settings() -> dict[str, Any]:
    return {
        "ocr_version": _env_text(PADDLE_OCR_VERSION_ENV, DEFAULT_PADDLE_OCR_VERSION),
        "text_detection_model_name": _env_text(
            PADDLE_OCR_DETECTION_MODEL_ENV,
            DEFAULT_PADDLE_OCR_DETECTION_MODEL,
        ),
        "text_recognition_model_name": _env_text(
            PADDLE_OCR_RECOGNITION_MODEL_ENV,
            DEFAULT_PADDLE_OCR_RECOGNITION_MODEL,
        ),
        "text_detection_model_dir": _env_optional_text(PADDLE_OCR_DETECTION_MODEL_DIR_ENV),
        "text_recognition_model_dir": _env_optional_text(PADDLE_OCR_RECOGNITION_MODEL_DIR_ENV),
        "use_textline_orientation": _env_bool(PADDLE_OCR_TEXTLINE_ORIENTATION_ENV, True),
        "use_doc_orientation_classify": _env_bool(PADDLE_OCR_DOC_ORIENTATION_ENV, False),
        "use_doc_unwarping": _env_bool(PADDLE_OCR_DOC_UNWARPING_ENV, False),
        "device": _env_text(PADDLE_OCR_DEVICE_ENV, "gpu"),
    }


def _env_text(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _env_optional_text(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return value.strip()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_ocr_engine() -> tuple[Any | None, str, str]:
    preferred = os.getenv(OCR_ENGINE_ENV, DEFAULT_OCR_ENGINE).strip().lower()
    engine_warning = ""
    if preferred and preferred not in {"paddle", "paddleocr", "auto"}:
        engine_warning = f"{OCR_ENGINE_ENV}={preferred} is no longer supported; using PaddleOCR."

    engine = _get_paddle_ocr_engine()
    if engine is not None:
        return engine, "paddleocr", engine_warning

    base_warning = "PaddleOCR is not installed or failed to initialize."
    if engine_warning:
        return None, "", f"{engine_warning} {base_warning}"
    return None, "", base_warning


def _get_formula_engine(enable_formula_recognition: bool):
    if not enable_formula_recognition:
        return None, ""
    try:
        from paddleocr import FormulaRecognition
    except Exception:
        return None, "Formula recognition is disabled because the PaddleOCR formula module is unavailable."

    _get_formula_engine._touched = True
    if getattr(_get_formula_engine, "_engine", None) is None:
        with PADDLE_OCR_LOCK:
            if getattr(_get_formula_engine, "_engine", None) is None:
                _get_formula_engine._engine = FormulaRecognition()
    return _get_formula_engine._engine, ""


def release_paddle_ocr_resources(clear_cached_engines: bool = True, force_clear_cache: bool = False) -> None:
    had_cached_engines = False
    if clear_cached_engines:
        with PADDLE_OCR_LOCK:
            had_cached_engines = (
                getattr(_get_paddle_ocr_engine, "_engine", None) is not None
                or getattr(_get_formula_engine, "_engine", None) is not None
                or getattr(_get_paddle_ocr_engine, "_touched", False)
                or getattr(_get_formula_engine, "_touched", False)
            )
            _get_paddle_ocr_engine._engine = None
            _get_formula_engine._engine = None
            _get_paddle_ocr_engine._touched = False
            _get_formula_engine._touched = False
    if force_clear_cache or had_cached_engines:
        _release_paddle_cuda_cache()


def _release_paddle_cuda_cache() -> None:
    gc.collect()
    try:
        import paddle
    except Exception:
        return

    try:
        paddle.device.synchronize()
    except Exception:
        pass
    try:
        paddle.device.empty_cache()
    except Exception:
        try:
            paddle.device.cuda.empty_cache()
        except Exception:
            pass
    gc.collect()


def _ocr_single_page(
    page: dict[str, Any],
    page_number: int,
    ocr_engine: Any,
    ocr_engine_name: str,
    formula_engine: Any,
    options: OCRPipelineOptions,
) -> OCRPageResult:
    pil_image = _load_image(page["image_bytes"])
    if pil_image is None:
        return OCRPageResult(
            page_number=page_number,
            width=page["width"],
            height=page["height"],
            text="",
            markdown="",
            warnings=["PIL is not installed or failed to decode page image."],
        )

    processed_image = _preprocess_image(
        pil_image,
        options=options,
    )
    image_input = _image_to_numpy(processed_image)
    if image_input is None:
        return OCRPageResult(
            page_number=page_number,
            width=page["width"],
            height=page["height"],
            text="",
            markdown="",
            warnings=["numpy is unavailable for OCR image conversion."],
        )

    try:
        with PADDLE_OCR_LOCK:
            raw_result = ocr_engine.predict(input=image_input)
    except Exception as exc:
        return OCRPageResult(
            page_number=page_number,
            width=page["width"],
            height=page["height"],
            text="",
            markdown="",
            warnings=[f"OCR prediction failed: {exc}"],
        )
    blocks = _extract_ocr_blocks(raw_result, page_number, processed_image.size)

    page_result = OCRPageResult(
        page_number=page_number,
        width=page["width"],
        height=page["height"],
        text="",
        markdown="",
        blocks=blocks,
        warnings=[] if blocks else [f"{ocr_engine_name} returned no text blocks."],
    )

    _remove_header_footer_noise(page_result, options)

    if formula_engine is not None:
        _attach_formula_results(page_result, formula_engine, processed_image, options.formula_confidence_threshold)

    _finalize_page_text(page_result)
    return page_result


def _load_image(image_bytes: bytes):
    try:
        from PIL import Image
    except Exception:
        return None
    return Image.open(io.BytesIO(image_bytes)).convert("RGB")


def _preprocess_image(pil_image, options: OCRPipelineOptions):
    image = pil_image.copy()
    width, height = image.size
    left = 0
    top = int(height * max(0.0, min(options.crop_header_ratio, 0.4)))
    right = width
    bottom = height - int(height * max(0.0, min(options.crop_footer_ratio, 0.4)))
    if top > 0 or bottom < height:
        image = image.crop((left, top, right, max(bottom, top + 1)))

    if options.trim_margins:
        image = _trim_blank_margins(image)

    if options.watermark_detection:
        image = _lighten_watermark_pixels(image, options.watermark_brightness_threshold)

    return image


def _trim_blank_margins(pil_image):
    try:
        from PIL import ImageChops
    except Exception:
        return pil_image

    background = pil_image.copy()
    background.paste((255, 255, 255), [0, 0, *pil_image.size])
    diff = ImageChops.difference(pil_image, background)
    bbox = diff.getbbox()
    if not bbox:
        return pil_image
    left, top, right, bottom = bbox
    padding = 6
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(pil_image.size[0], right + padding)
    bottom = min(pil_image.size[1], bottom + padding)
    return pil_image.crop((left, top, right, bottom))


def _lighten_watermark_pixels(pil_image, threshold: int):
    try:
        from PIL import Image
        import numpy as np
    except Exception:
        return pil_image

    arr = np.array(pil_image)
    brightness = arr.mean(axis=2)
    mask = brightness >= threshold
    arr[mask] = 255
    return Image.fromarray(arr)


def _image_to_numpy(pil_image):
    try:
        import numpy as np
    except Exception:
        return None
    return np.array(pil_image)


def _extract_ocr_blocks(raw_result: Any, page_number: int, image_size: tuple[int, int]) -> list[OCRTextBlock]:
    payload = _coerce_prediction_payload(raw_result)
    blocks: list[OCRTextBlock] = []
    width, height = image_size

    rec_boxes = _first_non_null(payload.get("rec_boxes"), payload.get("dt_polys"), [])
    rec_texts = _first_non_null(payload.get("rec_texts"), payload.get("texts"), [])
    rec_scores = _first_non_null(payload.get("rec_scores"), payload.get("scores"), [])

    max_len = max(len(rec_boxes), len(rec_texts), len(rec_scores))
    for idx in range(max_len):
        text = str(rec_texts[idx]).strip() if idx < len(rec_texts) else ""
        if not text:
            continue
        bbox = _normalize_bbox(rec_boxes[idx] if idx < len(rec_boxes) else None, width, height)
        score = _safe_float(rec_scores[idx]) if idx < len(rec_scores) else None
        blocks.append(
            OCRTextBlock(
                page_number=page_number,
                block_id=f"p{page_number}-b{idx + 1}",
                text=text,
                bbox=bbox,
                score=score,
            )
        )

    if blocks:
        return blocks

    nested_items = _first_non_null(payload.get("results"), payload.get("data"), [])
    for idx, item in enumerate(nested_items):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("rec_text") or "").strip()
        if not text:
            continue
        bbox = _normalize_bbox(item.get("bbox") or item.get("dt_poly"), width, height)
        blocks.append(
            OCRTextBlock(
                page_number=page_number,
                block_id=f"p{page_number}-b{idx + 1}",
                text=text,
                bbox=bbox,
                score=_safe_float(item.get("score") or item.get("rec_score")),
            )
        )
    return blocks


def _coerce_prediction_payload(raw_result: Any) -> dict[str, Any]:
    if isinstance(raw_result, list) and raw_result:
        first = raw_result[0]
        if isinstance(first, dict):
            return first
        if hasattr(first, "__dict__"):
            return dict(vars(first))
    if isinstance(raw_result, dict):
        return raw_result
    if hasattr(raw_result, "__dict__"):
        return dict(vars(raw_result))
    return {}


def _first_non_null(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _normalize_bbox(raw_bbox: Any, width: int, height: int) -> list[float]:
    if raw_bbox is None:
        return []
    if isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) == 4 and all(isinstance(v, (int, float)) for v in raw_bbox):
        x1, y1, x2, y2 = raw_bbox
        if x2 > 1 or y2 > 1:
            return [float(x1), float(y1), float(x2), float(y2)]
        return [float(x1 * width), float(y1 * height), float(x2 * width), float(y2 * height)]
    if isinstance(raw_bbox, (list, tuple)) and raw_bbox and isinstance(raw_bbox[0], (list, tuple)):
        xs = [float(pt[0]) for pt in raw_bbox if len(pt) >= 2]
        ys = [float(pt[1]) for pt in raw_bbox if len(pt) >= 2]
        if xs and ys:
            return [min(xs), min(ys), max(xs), max(ys)]
    return []


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _remove_header_footer_noise(page_result: OCRPageResult, options: OCRPipelineOptions) -> None:
    if not page_result.blocks:
        return

    kept: list[OCRTextBlock] = []
    for block in page_result.blocks:
        if not block.bbox:
            kept.append(block)
            continue

        x1, y1, x2, y2 = block.bbox
        page_height = max(1.0, max((b.bbox[3] for b in page_result.blocks if b.bbox), default=page_result.height))
        top_ratio = y1 / page_height
        bottom_ratio = 1.0 - (y2 / page_height)

        if options.crop_header_ratio > 0 and top_ratio <= options.crop_header_ratio + 0.01:
            block.removed_as_noise = True
            page_result.headers_removed.append(block.text)
            continue
        if options.crop_footer_ratio > 0 and bottom_ratio <= options.crop_footer_ratio + 0.01:
            block.removed_as_noise = True
            page_result.footers_removed.append(block.text)
            continue
        kept.append(block)

    page_result.blocks = kept


def _attach_formula_results(
    page_result: OCRPageResult,
    formula_engine: Any,
    pil_image: Any,
    min_confidence: float,
) -> None:
    for block in page_result.blocks:
        if not block.bbox:
            continue
        if not _looks_like_formula_text(block.text):
            continue
        cropped = _crop_block_image(pil_image, block.bbox)
        if cropped is None:
            continue
        try:
            with PADDLE_OCR_LOCK:
                prediction = formula_engine.predict(input=_image_to_numpy(cropped))
        except Exception as exc:
            page_result.warnings.append(f"Formula recognition failed on {block.block_id}: {exc}")
            continue

        formula_text, score = _extract_formula_prediction(prediction)
        if formula_text and (score is None or score >= min_confidence):
            block.block_type = "formula"
            block.latex = formula_text
            block.score = score if score is not None else block.score
            page_result.formulas.append(formula_text)


def _looks_like_formula_text(text: str) -> bool:
    if not text:
        return False
    symbol_hits = sum(1 for ch in text if ch in "=+-*/^()[]{}<>_")
    digit_hits = sum(1 for ch in text if ch.isdigit())
    return symbol_hits >= 2 or (digit_hits >= 2 and any(ch.isalpha() for ch in text))

def _crop_block_image(pil_image: Any, bbox: list[float]):
    if not bbox or len(bbox) != 4:
        return None
    x1, y1, x2, y2 = bbox
    width, height = pil_image.size
    pad = 6
    left = max(0, int(math.floor(x1 - pad)))
    top = max(0, int(math.floor(y1 - pad)))
    right = min(width, int(math.ceil(x2 + pad)))
    bottom = min(height, int(math.ceil(y2 + pad)))
    if right <= left or bottom <= top:
        return None
    return pil_image.crop((left, top, right, bottom))


def _extract_formula_prediction(prediction: Any) -> tuple[str, float | None]:
    payload = _coerce_prediction_payload(prediction)
    for text_key in ("rec_text", "text", "latex", "rec_formula", "formula"):
        text = str(payload.get(text_key) or "").strip()
        if text:
            return text, _safe_float(payload.get("score") or payload.get("rec_score"))

    if isinstance(prediction, list) and prediction:
        item = prediction[0]
        if isinstance(item, dict):
            for text_key in ("rec_text", "text", "latex", "rec_formula", "formula"):
                text = str(item.get(text_key) or "").strip()
                if text:
                    return text, _safe_float(item.get("score") or item.get("rec_score"))
    return "", None


def _remove_repeated_noise(page_results: list[OCRPageResult], min_pages: int) -> None:
    line_counter: Counter[str] = Counter()
    for page in page_results:
        unique_lines = {_normalize_noise_line(block.text) for block in page.blocks if block.text.strip()}
        for line in unique_lines:
            if line:
                line_counter[line] += 1

    repeated = {
        line
        for line, count in line_counter.items()
        if count >= min_pages and len(NOISE_TEXT_PATTERN.findall(line)) > 0 and len(line) <= 80
    }
    if not repeated:
        for page in page_results:
            _finalize_page_text(page)
        return

    for page in page_results:
        kept: list[OCRTextBlock] = []
        for block in page.blocks:
            normalized = _normalize_noise_line(block.text)
            if normalized in repeated:
                block.removed_as_noise = True
                page.repeated_noise_removed.append(block.text)
                continue
            kept.append(block)
        page.blocks = kept
        _finalize_page_text(page)


def _normalize_noise_line(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip())
    normalized = re.sub(r"\d+", "#", normalized)
    return normalized


def _finalize_page_text(page_result: OCRPageResult) -> None:
    ordered = sorted(page_result.blocks, key=_reading_order_key)
    lines: list[str] = []
    markdown_lines: list[str] = []
    for block in ordered:
        if block.removed_as_noise:
            continue
        text = block.latex if block.block_type == "formula" and block.latex else block.text
        if not text.strip():
            continue
        lines.append(text.strip())
        if block.block_type == "formula" and block.latex:
            markdown_lines.append(f"$$\n{block.latex}\n$$")
        else:
            markdown_lines.append(text.strip())

    page_result.text = "\n".join(lines).strip()
    page_result.markdown = "\n\n".join(markdown_lines).strip()


def _reading_order_key(block: OCRTextBlock) -> tuple[float, float, str]:
    if len(block.bbox) == 4:
        return (block.bbox[1], block.bbox[0], block.block_id)
    return (1e9, 1e9, block.block_id)
