from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

import library.parser as parser_module

from app.services.papers import _select_ai_cleanup_source
from library.parse_options import DocumentParseOptions
from library.parser import ParsedDocument, parse_document


def _build_ocr_document() -> ParsedDocument:
    text = "第1页\n单项选择题\n1. 测试题目\n版权所有"
    return ParsedDocument(
        text=text,
        markdown=text,
        provider="pdf_ocr_pipeline",
        used_ocr=True,
    )


def test_raw_ocr_mode_disables_repeated_line_cleanup_in_pipeline_options() -> None:
    options = DocumentParseOptions(raw_ocr_mode=True)

    pipeline_options = options.to_pipeline_options()

    assert pipeline_options.remove_repeated_lines is False


def test_v3_preset_uses_structure_pipeline_defaults() -> None:
    options = DocumentParseOptions(preset="v3")

    pipeline_options = options.to_pipeline_options()

    assert options.should_use_layout_pipeline() is True
    assert pipeline_options.render_dpi == 320
    assert pipeline_options.enable_formula_recognition is False


def test_parse_document_raw_ocr_mode_skips_ocr_rule_cleanup(monkeypatch) -> None:
    monkeypatch.setattr(parser_module, "_parse_pdf_with_options", lambda *args, **kwargs: _build_ocr_document())

    raw_result = parse_document(
        b"%PDF-1.7",
        "sample.pdf",
        "application/pdf",
        options=DocumentParseOptions(raw_ocr_mode=True),
    )
    cleaned_result = parse_document(
        b"%PDF-1.7",
        "sample.pdf",
        "application/pdf",
        options=DocumentParseOptions(),
    )

    assert "第1页" in raw_result.text
    assert "版权所有" in raw_result.text
    assert raw_result.cleanup_report == {}
    assert raw_result.cleanup_score is None
    assert raw_result.raw_text == raw_result.text
    assert "第1页" not in cleaned_result.text
    assert "版权所有" not in cleaned_result.text


def test_select_ai_cleanup_source_prefers_raw_ocr_snapshot() -> None:
    document = ParsedDocument(
        text="规则清噪后的正文",
        markdown="规则清噪后的正文",
        provider="pdf_ocr_pipeline",
        used_ocr=True,
        raw_text="原始 OCR 文本",
        raw_markdown="原始 OCR Markdown",
    )

    markdown_source, markdown_raw_source = _select_ai_cleanup_source(
        document,
        DocumentParseOptions(output_format="markdown", raw_ocr_mode=True),
    )
    text_source, text_raw_source = _select_ai_cleanup_source(
        document,
        DocumentParseOptions(output_format="text", raw_ocr_mode=True),
    )

    assert markdown_source == "原始 OCR Markdown"
    assert markdown_raw_source == "原始 OCR 文本"
    assert text_source == "原始 OCR 文本"
    assert text_raw_source == "原始 OCR 文本"


def test_parse_document_can_strip_pdf_embedded_image_content(monkeypatch) -> None:
    monkeypatch.setattr(
        parser_module,
        "_parse_pdf_with_options",
        lambda *args, **kwargs: ParsedDocument(
            text='题干\n<img src="imgs/page_0001/chart.png">',
            markdown='题干\n![图表](imgs/page_0001/chart.png)',
            provider="pp_structure_v3",
            used_ocr=True,
            pages=[
                parser_module.ParsedPage(
                    page_number=1,
                    text='题干\n<img src="imgs/page_0001/chart.png">',
                    markdown='题干\n![图表](imgs/page_0001/chart.png)',
                )
            ],
            raw_text='题干\nimgs/page_0001/chart.png',
            raw_markdown='题干\n![图表](imgs/page_0001/chart.png)',
            markdown_image_roots=["C:/fake/assets"],
            markdown_images={"imgs/page_0001/chart.png": object()},
        ),
    )

    result = parse_document(
        b"%PDF-1.7",
        "sample.pdf",
        "application/pdf",
        options=DocumentParseOptions(preserve_pdf_image_content=False),
    )

    assert result.text == "题干"
    assert result.markdown == "题干"
    assert result.raw_markdown == "题干"
    assert result.raw_text == "题干"
    assert result.markdown_image_roots == []
    assert result.markdown_images == {}


def test_parse_document_keeps_pdf_embedded_image_content_by_default(monkeypatch) -> None:
    monkeypatch.setattr(
        parser_module,
        "_parse_pdf_with_options",
        lambda *args, **kwargs: ParsedDocument(
            text="题干\nimgs/page_0001/chart.png",
            markdown='题干\n![图表](imgs/page_0001/chart.png)',
            provider="pp_structure_v3",
            used_ocr=True,
            markdown_image_roots=["C:/fake/assets"],
            markdown_images={"imgs/page_0001/chart.png": object()},
        ),
    )

    result = parse_document(
        b"%PDF-1.7",
        "sample.pdf",
        "application/pdf",
        options=DocumentParseOptions(raw_ocr_mode=True),
    )

    assert "imgs/page_0001/chart.png" in result.markdown
    assert result.provider == "pp_structure_v3"
    assert result.used_ocr is True
