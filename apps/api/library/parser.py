from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

from library.parse_options import DocumentParseOptions
from library.pdf_ocr_pipeline import (
    OCRPipelineOptions,
    PADDLE_OCR_LOCK,
    _get_paddle_ocr_settings,
    release_paddle_ocr_resources,
    run_pdf_ocr_pipeline,
)


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
TEXT_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")
PDF_TEXT_CHAR_THRESHOLD = 24
PDF_OCR_PREVIEW_MAX_PAGES = 2
ParseProgressCallback = Callable[[str, int, dict[str, object] | None], None]


@dataclass
class ParsedTable:
    page: int | None = None
    markdown: str = ""
    html: str = ""


@dataclass
class ParsedPage:
    page_number: int
    text: str = ""
    markdown: str = ""


@dataclass
class ParsedDocument:
    text: str
    markdown: str
    provider: str
    used_ocr: bool = False
    pages: list[ParsedPage] = field(default_factory=list)
    tables: list[ParsedTable] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_bytes(
    data: bytes,
    filename: str,
    mime: str,
    options: DocumentParseOptions | None = None,
) -> str:
    return parse_document(data, filename, mime, options=options).text


def parse_document(
    data: bytes,
    filename: str,
    mime: str,
    options: DocumentParseOptions | None = None,
    progress_callback: ParseProgressCallback | None = None,
) -> ParsedDocument:
    try:
        options = options or DocumentParseOptions()
        suffix = Path(filename).suffix.lower()

        if options.should_use_pdf_ocr(filename, mime):
            return _parse_pdf_with_options(data, filename, options, progress_callback=progress_callback)
        if suffix == ".pdf" or mime == "application/pdf":
            return _parse_pdf(data, filename, progress_callback=progress_callback)
        if suffix in {".docx", ".doc"}:
            return _parse_docx(data)
        if suffix in IMAGE_SUFFIXES or mime.startswith("image/"):
            return _parse_image(data, suffix or ".png")
        return _parse_text_document(data)
    finally:
        release_paddle_parser_resources()


def parse_preview_document(
    data: bytes,
    filename: str,
    mime: str,
    options: DocumentParseOptions | None = None,
) -> ParsedDocument:
    try:
        options = options or DocumentParseOptions()
        suffix = Path(filename).suffix.lower()
        is_pdf = suffix == ".pdf" or mime == "application/pdf"
        if is_pdf and options.is_default():
            direct = _extract_selectable_pdf_text(data)
            if direct is not None and _document_has_meaningful_text(direct):
                direct.provider = "pymupdf_text"
                direct.used_ocr = False
                return direct

            warning = (
                "未检测到可直接提取的 PDF 文本。该文件可能是扫描件；"
                "如需完整解析，请在素材库中选择 OCR 预设或开启强制 OCR。"
            )
            if direct is not None:
                direct.provider = "pymupdf_text_preview"
                direct.used_ocr = False
                direct.warnings.append(warning)
                return direct
            return ParsedDocument(text="", markdown="", provider="pymupdf_text_preview", warnings=[warning])

        if is_pdf and options.should_use_pdf_ocr(filename, mime):
            return _parse_pdf_with_options(data, filename, options, max_pages=PDF_OCR_PREVIEW_MAX_PAGES)

        return _parse_document_inner(data, filename, mime, options=options)
    finally:
        release_paddle_parser_resources()


def _parse_document_inner(
    data: bytes,
    filename: str,
    mime: str,
    options: DocumentParseOptions | None = None,
    progress_callback: ParseProgressCallback | None = None,
) -> ParsedDocument:
    options = options or DocumentParseOptions()
    suffix = Path(filename).suffix.lower()

    if options.should_use_pdf_ocr(filename, mime):
        return _parse_pdf_with_options(data, filename, options, progress_callback=progress_callback)
    if suffix == ".pdf" or mime == "application/pdf":
        return _parse_pdf(data, filename, progress_callback=progress_callback)
    if suffix in {".docx", ".doc"}:
        return _parse_docx(data)
    if suffix in IMAGE_SUFFIXES or mime.startswith("image/"):
        return _parse_image(data, suffix or ".png")
    return _parse_text_document(data)


def serialize_parsed_document(document: ParsedDocument) -> str:
    return json.dumps(document.to_dict(), ensure_ascii=False)


def deserialize_parsed_document(payload: str) -> ParsedDocument | None:
    try:
        raw = json.loads(payload)
    except (TypeError, ValueError):
        return None

    if not isinstance(raw, dict):
        return None

    pages = [
        ParsedPage(
            page_number=int(item.get("page_number", index + 1)),
            text=str(item.get("text") or ""),
            markdown=str(item.get("markdown") or ""),
        )
        for index, item in enumerate(raw.get("pages") or [])
        if isinstance(item, dict)
    ]
    tables = [
        ParsedTable(
            page=item.get("page"),
            markdown=str(item.get("markdown") or ""),
            html=str(item.get("html") or ""),
        )
        for item in raw.get("tables") or []
        if isinstance(item, dict)
    ]
    return ParsedDocument(
        text=str(raw.get("text") or ""),
        markdown=str(raw.get("markdown") or ""),
        provider=str(raw.get("provider") or "unknown"),
        used_ocr=bool(raw.get("used_ocr")),
        pages=pages,
        tables=tables,
        warnings=[str(item) for item in raw.get("warnings") or [] if str(item).strip()],
    )


def _parse_pdf_with_options(
    data: bytes,
    filename: str,
    options: DocumentParseOptions,
    max_pages: int | None = None,
    progress_callback: ParseProgressCallback | None = None,
) -> ParsedDocument:
    with PADDLE_OCR_LOCK:
        pipeline_options = options.to_pipeline_options()
        if max_pages is not None:
            pipeline_options.max_pages = max_pages
        layout_result: ParsedDocument | None = None
        layout_score = 0.0
        if options.should_use_layout_pipeline():
            layout_result = _parse_pdf_with_pp_structure(data, filename, pipeline_options, progress_callback)
            if layout_result is not None and _document_has_meaningful_text(layout_result):
                layout_result.warnings.insert(0, f"parse_preset={options.preset}")
                layout_score = _document_quality_score(layout_result)
                if layout_score >= 6.5:
                    return layout_result
                layout_result.warnings.append(
                    f"PP-StructureV3 quality score {layout_score:.2f} below gate; trying PP-OCRv5 fallback."
                )

        result = run_pdf_ocr_pipeline(
            data,
            filename,
            options=pipeline_options,
            progress_callback=_ocr_progress_callback(
                progress_callback,
                stage="ocr_fallback" if layout_result is not None else "ocr",
                start=70 if layout_result is not None else 15,
                end=75 if layout_result is not None else 70,
            ),
        )
        ocr_document = _document_from_ocr_result(result, warnings_prefix=[f"parse_preset={options.preset}"])
        if layout_result is not None and _document_has_meaningful_text(layout_result):
            ocr_score = _document_quality_score(ocr_document)
            if ocr_score >= layout_score:
                ocr_document.warnings.insert(
                    1,
                    f"PP-OCRv5 fallback selected over PP-StructureV3 ({ocr_score:.2f} >= {layout_score:.2f}).",
                )
                return ocr_document
            layout_result.warnings.append(
                f"PP-StructureV3 selected over PP-OCRv5 fallback ({layout_score:.2f} > {ocr_score:.2f})."
            )
            return layout_result
        return ocr_document


def _document_from_ocr_result(result: Any, warnings_prefix: list[str] | None = None) -> ParsedDocument:
    pages = [
        ParsedPage(page_number=page.page_number, text=page.text, markdown=page.markdown)
        for page in result.pages
    ]
    warnings = [*(warnings_prefix or []), *result.warnings]
    for page in result.pages:
        warnings.extend([warning for warning in page.warnings if warning.strip()])
    return ParsedDocument(
        text=result.text,
        markdown=result.markdown,
        provider=result.provider,
        used_ocr=result.used_ocr,
        pages=pages,
        tables=[],
        warnings=warnings,
    )


def _parse_pdf(
    data: bytes,
    filename: str,
    progress_callback: ParseProgressCallback | None = None,
) -> ParsedDocument:
    direct = _extract_selectable_pdf_text(data)
    if direct is not None and _document_has_meaningful_text(direct):
        direct.provider = "pymupdf_text"
        direct.used_ocr = False
        return direct

    parsed = _document_from_ocr_result(
        run_pdf_ocr_pipeline(
            data,
            filename,
            options=OCRPipelineOptions(
                force_ocr=True,
                render_dpi=240,
                trim_margins=True,
                remove_repeated_lines=True,
                watermark_detection=False,
            ),
            progress_callback=_ocr_progress_callback(progress_callback),
        ),
        warnings_prefix=["parse_preset=auto_ocr_fallback"],
    )
    if _document_has_meaningful_text(parsed):
        if direct is not None:
            parsed.warnings.insert(0, "Selectable PDF text was insufficient; OCR fallback was used.")
        return parsed

    warnings = ["Selectable PDF text was insufficient and OCR fallback returned no text."]
    warnings.extend(parsed.warnings)
    if direct is not None:
        direct.warnings.extend(warnings)
        return direct
    return ParsedDocument(text="", markdown="", provider="unavailable", warnings=warnings)


def _ocr_progress_callback(
    progress_callback: ParseProgressCallback | None,
    *,
    stage: str = "ocr",
    start: int = 15,
    end: int = 70,
):
    if progress_callback is None:
        return None

    def on_page(done_pages: int, total_pages: int) -> None:
        progress_callback(
            stage,
            min(end, start + int((done_pages / max(1, total_pages)) * max(1, end - start))),
            {"done_pages": done_pages, "total_pages": total_pages},
        )

    return on_page


def _parse_docx(data: bytes) -> ParsedDocument:
    try:
        from docx import Document

        document = Document(BytesIO(data))
        paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
        text = "\n".join(paragraphs)
        return ParsedDocument(text=text, markdown=text, provider="docx_text")
    except Exception as exc:
        warning = f"[DOCX parse failed: {exc}]"
        return ParsedDocument(text=warning, markdown=warning, provider="docx_text", warnings=[warning])


def _parse_image(data: bytes, suffix: str) -> ParsedDocument:
    with PADDLE_OCR_LOCK:
        parsed = _parse_with_pp_structure(data, suffix or ".png")
        if parsed is not None:
            return parsed
        return ParsedDocument(
            text="",
            markdown="",
            provider="unavailable",
            used_ocr=False,
            warnings=["PP-StructureV3 is unavailable for image OCR."],
        )


def _parse_pdf_with_pp_structure(
    data: bytes,
    filename: str,
    options: OCRPipelineOptions,
    progress_callback: ParseProgressCallback | None = None,
) -> ParsedDocument | None:
    try:
        pages, total_page_count = _render_pdf_pages_for_layout(data, options.render_dpi, options.max_pages)
    except Exception as exc:
        return ParsedDocument(
            text="",
            markdown="",
            provider="pp_structure_v3",
            used_ocr=True,
            warnings=[f"PP-StructureV3 PDF render failed: {exc}"],
        )

    if not pages:
        return ParsedDocument(
            text="",
            markdown="",
            provider="pp_structure_v3",
            used_ocr=True,
            warnings=["PP-StructureV3 PDF render returned no pages."],
        )

    page_docs: list[ParsedDocument] = []
    warnings: list[str] = []
    for index, page in enumerate(pages, start=1):
        if progress_callback is not None:
            progress_callback("layout_analysis", min(70, 15 + int((index / max(1, len(pages))) * 55)), {"done_pages": index, "total_pages": len(pages)})
        page_doc = _parse_with_pp_structure(
            page["image_bytes"],
            ".png",
            enable_formula_recognition=options.enable_formula_recognition,
        )
        if page_doc is None:
            warnings.append(f"PP-StructureV3 unavailable on page {index}.")
            continue
        if page_doc.warnings:
            warnings.extend(f"page {index}: {warning}" for warning in page_doc.warnings)
        for parsed_page in page_doc.pages:
            parsed_page.page_number = index
        for table in page_doc.tables:
            table.page = index
        page_docs.append(page_doc)

    if not page_docs:
        return ParsedDocument(
            text="",
            markdown="",
            provider="pp_structure_v3",
            used_ocr=True,
            warnings=warnings or ["PP-StructureV3 returned no page documents."],
        )

    pages_out = [page for doc in page_docs for page in doc.pages]
    tables = [table for doc in page_docs for table in doc.tables]
    text = "\n\n".join(doc.text for doc in page_docs if doc.text.strip())
    markdown = "\n\n".join(doc.markdown for doc in page_docs if doc.markdown.strip())
    if options.max_pages is not None and total_page_count > len(pages):
        warnings.append(f"Layout analysis limited to first {len(pages)} of {total_page_count} pages.")
    return ParsedDocument(
        text=text,
        markdown=markdown or text,
        provider="pp_structure_v3",
        used_ocr=True,
        pages=pages_out,
        tables=tables,
        warnings=warnings,
    )


def _render_pdf_pages_for_layout(pdf_bytes: bytes, dpi: int, max_pages: int | None = None) -> tuple[list[dict[str, Any]], int]:
    try:
        import pymupdf
    except Exception:
        import fitz as pymupdf

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    scale = dpi / 72.0
    matrix = pymupdf.Matrix(scale, scale)
    pages: list[dict[str, Any]] = []
    for page_index, page in enumerate(doc):
        if max_pages is not None and page_index >= max_pages:
            break
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        pages.append({"image_bytes": pix.tobytes("png")})
    return pages, doc.page_count


def _parse_text_document(data: bytes) -> ParsedDocument:
    text = _parse_text(data)
    return ParsedDocument(text=text, markdown=text, provider="plain_text")


def _parse_text(data: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _extract_selectable_pdf_text(data: bytes) -> ParsedDocument | None:
    try:
        import fitz

        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        return ParsedDocument(
            text="",
            markdown="",
            provider="pymupdf_text",
            warnings=[f"PyMuPDF text extraction failed: {exc}"],
        )

    pages: list[ParsedPage] = []
    page_texts: list[str] = []
    for index, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        pages.append(ParsedPage(page_number=index, text=text, markdown=text))
        if text:
            page_texts.append(text)

    merged = "\n\n".join(page_texts)
    return ParsedDocument(
        text=merged,
        markdown=merged,
        provider="pymupdf_text",
        used_ocr=False,
        pages=pages,
    )


def _document_has_meaningful_text(document: ParsedDocument | None) -> bool:
    if document is None:
        return False
    return len(TEXT_CHAR_PATTERN.findall(document.text or "")) >= PDF_TEXT_CHAR_THRESHOLD


def _document_quality_score(document: ParsedDocument) -> float:
    text = (document.markdown or document.text or "").strip()
    if not text:
        return 0.0
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text_chars = len(TEXT_CHAR_PATTERN.findall(text))
    question_hits = len(re.findall(r"(?m)^\s*\d{1,3}\s*[\.、．)]", text))
    option_hits = len(re.findall(r"(?m)^\s*[A-H][\.\、．)]", text))
    answer_hits = len(re.findall(r"(?:答案|参考答案|正确答案)\s*[:：]", text))
    analysis_hits = len(re.findall(r"(?:解析|答案解析|【解析】)\s*[:：]", text))
    short_line_ratio = (
        sum(1 for line in lines if len(TEXT_CHAR_PATTERN.findall(line)) <= 3) / max(1, len(lines))
    )
    score = 0.0
    score += min(3.0, text_chars / 160)
    score += min(3.0, question_hits * 0.9)
    score += min(2.0, option_hits * 0.25)
    score += min(1.0, answer_hits * 0.5)
    score += min(1.0, analysis_hits * 0.5)
    score -= min(2.0, short_line_ratio * 2.0)
    return max(0.0, round(score, 2))


def _parse_with_pp_structure(
    data: bytes,
    suffix: str,
    *,
    enable_formula_recognition: bool = False,
) -> ParsedDocument | None:
    pipeline = _get_pp_structure_pipeline()
    if pipeline is None:
        return None

    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(data)
            tmp.flush()
        results = _predict_pp_structure(
            pipeline,
            tmp_path,
            enable_formula_recognition=enable_formula_recognition,
        )
    except Exception as exc:
        return ParsedDocument(
            text="",
            markdown="",
            provider="pp_structure_v3",
            used_ocr=True,
            warnings=[f"PP-StructureV3 parse failed: {exc}"],
        )
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    return _document_from_pp_results(results, provider="pp_structure_v3")


def _predict_pp_structure(pipeline: Any, input_path: str, *, enable_formula_recognition: bool):
    with PADDLE_OCR_LOCK:
        return list(
            pipeline.predict(
                input=input_path,
                use_textline_orientation=True,
                use_table_recognition=True,
                use_formula_recognition=enable_formula_recognition,
            )
        )


def _document_from_pp_results(results: list[Any], provider: str) -> ParsedDocument:
    pages: list[ParsedPage] = []
    tables: list[ParsedTable] = []
    warnings: list[str] = []
    text_parts: list[str] = []
    markdown_parts: list[str] = []

    for page_index, result in enumerate(results, start=1):
        text = _extract_pp_text(result).strip()
        markdown = _extract_pp_markdown(result).strip()
        page_tables = _extract_pp_tables(result, page_index)
        tables.extend(page_tables)
        text = _dedupe_table_markup(text, page_tables)
        markdown = _dedupe_table_markup(markdown, page_tables)
        pages.append(ParsedPage(page_number=page_index, text=text, markdown=markdown or text))
        if text:
            text_parts.append(text)
        if markdown:
            markdown_parts.append(markdown)
        elif text:
            markdown_parts.append(text)

    merged_text = "\n\n".join(part for part in text_parts if part)
    merged_markdown = "\n\n".join(part for part in markdown_parts if part)
    if not merged_text and not merged_markdown:
        warnings.append("PP-StructureV3 returned no textual content.")

    return ParsedDocument(
        text=merged_text or _markdown_to_text(merged_markdown),
        markdown=merged_markdown or merged_text,
        provider=provider,
        used_ocr=True,
        pages=pages,
        tables=tables,
        warnings=warnings,
    )


def _extract_pp_text(result: Any) -> str:
    for candidate in (
        getattr(result, "text", None),
        getattr(result, "markdown", None),
        getattr(result, "rec_texts", None),
        getattr(result, "texts", None),
    ):
        normalized = _normalize_text_candidate(candidate)
        if normalized.strip():
            return _markdown_to_text(normalized)

    payload = _result_to_dict(result)
    for key in ("text", "markdown", "rec_texts", "texts"):
        normalized = _normalize_text_candidate(payload.get(key))
        if normalized.strip():
            return _markdown_to_text(normalized)

    outputs = payload.get("parsing_res_list") or payload.get("layout_parsing_result") or payload.get("results")
    return _collect_text_from_blocks(outputs)


def _extract_pp_markdown(result: Any) -> str:
    markdown = _extract_markdown_payload(getattr(result, "markdown", None))
    if markdown.strip():
        return markdown

    payload = _result_to_dict(result)
    for key in ("markdown", "md"):
        markdown = _extract_markdown_payload(payload.get(key))
        if markdown.strip():
            return markdown

    outputs = payload.get("parsing_res_list") or payload.get("layout_parsing_result") or payload.get("results")
    return _collect_markdown_from_blocks(outputs)


def _extract_pp_tables(result: Any, page_number: int) -> list[ParsedTable]:
    payload = _result_to_dict(result)
    tables: list[ParsedTable] = []
    table_res_list = payload.get("table_res_list")
    if isinstance(table_res_list, list):
        for item in table_res_list:
            if not isinstance(item, dict):
                continue
            html = _normalize_text_candidate(item.get("pred_html") or item.get("html") or item.get("table_html"))
            markdown = _normalize_text_candidate(item.get("pred_markdown") or item.get("markdown") or item.get("table_markdown"))
            if html or markdown:
                tables.append(ParsedTable(page=page_number, markdown=markdown, html=html))

    outputs = payload.get("parsing_res_list") or payload.get("layout_parsing_result") or payload.get("results")
    if not isinstance(outputs, list):
        return tables

    for item in outputs:
        if not isinstance(item, dict):
            continue
        block_type = str(item.get("block_label") or item.get("type") or "").lower()
        if "table" not in block_type:
            continue
        markdown = _normalize_text_candidate(
            item.get("markdown") or item.get("table_markdown") or item.get("pred_markdown")
        )
        html = _normalize_text_candidate(item.get("html") or item.get("table_html") or item.get("pred_html"))
        if markdown or html:
            signature = (markdown.strip(), html.strip())
            if not any((existing.markdown.strip(), existing.html.strip()) == signature for existing in tables):
                tables.append(ParsedTable(page=page_number, markdown=markdown, html=html))
    return tables


def _result_to_dict(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    if hasattr(result, "__dict__"):
        return dict(vars(result))
    return {}


def _collect_text_from_blocks(outputs: Any) -> str:
    if not isinstance(outputs, list):
        return ""
    lines: list[str] = []
    for item in outputs:
        if not isinstance(item, dict):
            continue
        for key in ("text", "markdown", "content", "result", "latex"):
            value = _normalize_text_candidate(item.get(key))
            if value.strip():
                lines.append(_markdown_to_text(value))
                break
    return "\n".join(line for line in lines if line).strip()


def _collect_markdown_from_blocks(outputs: Any) -> str:
    if not isinstance(outputs, list):
        return ""
    blocks: list[str] = []
    for item in outputs:
        if not isinstance(item, dict):
            continue
        value = _normalize_text_candidate(
            item.get("markdown") or item.get("table_markdown") or item.get("content") or item.get("text")
        )
        if value.strip():
            blocks.append(value)
    return "\n\n".join(block for block in blocks if block).strip()


def _normalize_text_candidate(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        preferred = []
        for key in ("markdown_texts", "text", "block_content", "content"):
            item = value.get(key)
            text = _normalize_text_candidate(item)
            if text:
                preferred.append(text)
        if preferred:
            return "\n".join(preferred).strip()
        return str(value).strip()
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        parts = [_normalize_text_candidate(item) for item in value]
        return "\n".join(part for part in parts if part).strip()
    return str(value).strip()


def _markdown_to_text(markdown: str) -> str:
    if not markdown:
        return ""
    text = markdown
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^[>#\-\*\s|]+", "", text, flags=re.M)
    text = re.sub(r"\|", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_markdown_payload(value: Any) -> str:
    if isinstance(value, dict):
        return _normalize_text_candidate(value.get("markdown_texts") or value.get("text") or value)
    return _normalize_text_candidate(value)


def _dedupe_table_markup(content: str, tables: list[ParsedTable]) -> str:
    if not content:
        return content
    normalized = content
    for table in tables:
        html = (table.html or "").strip()
        if html:
            normalized = normalized.replace(html, "").replace(f"<div style=\"text-align: center;\">{html}</div>", "")
        markdown = (table.markdown or "").strip()
        if markdown:
            normalized = normalized.replace(markdown, "")
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _get_pp_structure_pipeline():
    try:
        _patch_paddleocr_common_args()
        from paddleocr import PPStructureV3
    except Exception:
        return None

    if getattr(_get_pp_structure_pipeline, "_pipeline", None) is None:
        with PADDLE_OCR_LOCK:
            if getattr(_get_pp_structure_pipeline, "_pipeline", None) is None:
                _get_pp_structure_pipeline._touched = True
                ocr_settings = _get_paddle_ocr_settings()
                pipeline = PPStructureV3(
                    device=str(ocr_settings["device"]),
                    enable_hpi=False,
                    use_tensorrt=False,
                    enable_mkldnn=False,
                    cpu_threads=4,
                    text_detection_model_name=ocr_settings["text_detection_model_name"],
                    text_recognition_model_name=ocr_settings["text_recognition_model_name"],
                    text_rec_score_thresh=0.0,
                )
                _get_pp_structure_pipeline._pipeline = pipeline
    return _get_pp_structure_pipeline._pipeline


def release_paddle_parser_resources() -> None:
    with PADDLE_OCR_LOCK:
        had_pp_structure = (
            getattr(_get_pp_structure_pipeline, "_pipeline", None) is not None
            or getattr(_get_pp_structure_pipeline, "_touched", False)
        )
        _get_pp_structure_pipeline._pipeline = None
        _get_pp_structure_pipeline._touched = False
        release_paddle_ocr_resources(force_clear_cache=had_pp_structure)


def _patch_paddleocr_common_args() -> None:
    if getattr(_patch_paddleocr_common_args, "_patched", False):
        return

    try:
        from paddlex.inference import PaddlePredictorOption
        from paddlex.utils.device import get_default_device, parse_device
        from paddleocr import _common_args as common_args
    except Exception:
        return

    def prepare_common_init_args(model_name, common_args_dict):
        device = common_args_dict["device"]
        if device is None:
            device = get_default_device()
        device_type, device_ids = parse_device(device)
        device_id = device_ids[0] if device_ids is not None else None

        init_kwargs = {
            "use_hpip": common_args_dict["enable_hpi"],
            "hpi_config": {"device_type": device_type, "device_id": device_id},
        }
        pp_option = PaddlePredictorOption(device_type=device_type, device_id=device_id)
        if model_name:
            pp_option.setdefault_by_model_name(model_name)

        if device_type == "gpu":
            if common_args_dict["use_pptrt"]:
                if common_args_dict["pptrt_precision"] == "fp32":
                    pp_option.run_mode = "trt_fp32"
                else:
                    pp_option.run_mode = "trt_fp16"
            else:
                pp_option.run_mode = "paddle"
        elif device_type == "cpu":
            if common_args_dict["enable_mkldnn"]:
                pp_option.run_mode = "mkldnn"
                pp_option.mkldnn_cache_capacity = common_args_dict["mkldnn_cache_capacity"]
            else:
                pp_option.run_mode = "paddle"
            pp_option.cpu_threads = common_args_dict["cpu_threads"]
        else:
            pp_option.run_mode = "paddle"

        init_kwargs["pp_option"] = pp_option
        return init_kwargs

    common_args.prepare_common_init_args = prepare_common_init_args
    _patch_paddleocr_common_args._patched = True
