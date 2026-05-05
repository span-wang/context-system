from __future__ import annotations

import re
import tempfile
from functools import lru_cache
from io import BytesIO
from pathlib import Path


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
PDF_TEXT_CHAR_THRESHOLD = 24
TEXT_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")


def parse_bytes(data: bytes, filename: str, mime: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf" or mime == "application/pdf":
        return _parse_pdf(data)
    if suffix in {".docx", ".doc"}:
        return _parse_docx(data)
    if suffix in IMAGE_SUFFIXES or mime.startswith("image/"):
        return _parse_image(data, suffix)
    return _parse_text(data)


def _parse_text(data: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _parse_pdf(data: bytes) -> str:
    try:
        import fitz

        doc = fitz.open(stream=data, filetype="pdf")
        page_texts: list[str] = []
        for page in doc:
            text = page.get_text("text").strip()
            if _has_meaningful_text(text):
                page_texts.append(text)
                continue

            ocr_text = _ocr_pdf_page(page)
            if ocr_text:
                page_texts.append(ocr_text)
        return "\n\n".join(text for text in page_texts if text)
    except Exception as exc:
        return f"[PDF 解析失败: {exc}]"


def _parse_docx(data: bytes) -> str:
    try:
        from docx import Document

        document = Document(BytesIO(data))
        paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)
    except Exception as exc:
        return f"[DOCX 解析失败: {exc}]"


def _parse_image(data: bytes, suffix: str) -> str:
    return _ocr_bytes_via_temp_file(data, suffix or ".png")


def _ocr_pdf_page(page) -> str:
    try:
        pixmap = page.get_pixmap(dpi=200, alpha=False)
        return _ocr_bytes_via_temp_file(pixmap.tobytes("png"), ".png")
    except Exception:
        return ""


def _ocr_bytes_via_temp_file(data: bytes, suffix: str) -> str:
    engine = _get_ocr_engine()
    if engine is None:
        return ""

    try:
        with tempfile.NamedTemporaryFile(delete=True, suffix=suffix) as tmp:
            tmp.write(data)
            tmp.flush()
            result = engine(tmp.name)
    except Exception:
        return ""
    return _extract_ocr_text(result)


def _extract_ocr_text(result: object) -> str:
    if result is None:
        return ""

    txts = getattr(result, "txts", None)
    if txts:
        return "\n".join(str(text).strip() for text in txts if str(text).strip())

    if isinstance(result, tuple) and result:
        primary = result[0]
        if hasattr(primary, "txts"):
            return _extract_ocr_text(primary)
        if isinstance(primary, list):
            lines: list[str] = []
            for item in primary:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue
                candidate = item[1]
                if isinstance(candidate, (list, tuple)) and candidate:
                    candidate = candidate[0]
                text = str(candidate).strip()
                if text:
                    lines.append(text)
            if lines:
                return "\n".join(lines)
    return ""


def _has_meaningful_text(text: str) -> bool:
    return len(TEXT_CHAR_PATTERN.findall(text)) >= PDF_TEXT_CHAR_THRESHOLD


@lru_cache(maxsize=1)
def _get_ocr_engine():
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception:
        try:
            from rapidocr import RapidOCR
        except Exception:
            return None

    try:
        return RapidOCR()
    except Exception:
        return None
