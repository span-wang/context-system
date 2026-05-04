from __future__ import annotations

from pathlib import Path


def parse_bytes(data: bytes, filename: str, mime: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf" or mime == "application/pdf":
        return _parse_pdf(data)
    if suffix in {".docx", ".doc"}:
        return _parse_docx(data)
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
        pages = [page.get_text("text").strip() for page in doc]
        return "\n\n".join(page for page in pages if page)
    except Exception as exc:
        return f"[PDF 解析失败: {exc}]"


def _parse_docx(data: bytes) -> str:
    try:
        from docx import Document
        from io import BytesIO

        document = Document(BytesIO(data))
        paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)
    except Exception as exc:
        return f"[DOCX 解析失败: {exc}]"

