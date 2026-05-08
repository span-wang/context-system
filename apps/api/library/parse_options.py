from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from library.pdf_ocr_pipeline import OCRPipelineOptions


ParsePreset = Literal["auto", "fast", "balanced", "accurate", "formula"]
ParseOutputFormat = Literal["markdown", "text"]


class DocumentParseOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset: ParsePreset = "auto"
    output_format: ParseOutputFormat = "markdown"
    force_ocr: bool | None = None
    render_dpi: int | None = Field(default=None, ge=96, le=300)
    crop_header_ratio: float | None = Field(default=None, ge=0.0, le=0.2)
    crop_footer_ratio: float | None = Field(default=None, ge=0.0, le=0.2)
    trim_margins: bool | None = None
    remove_repeated_lines: bool | None = None
    watermark_detection: bool | None = None
    enable_formula_recognition: bool | None = None
    pdf_page_chunk_size: int | None = Field(default=None, ge=1, le=50)

    def should_use_layout_pipeline(self) -> bool:
        return self.preset in {"accurate", "formula"}

    def is_default(self) -> bool:
        return self._parse_behavior_dump() == {"preset": "auto"}

    def normalized_dump(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)

    def cache_key(self) -> str:
        if self.is_default():
            return "default"
        payload = json.dumps(self._parse_behavior_dump(), ensure_ascii=False, sort_keys=True)
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]

    def select_output(self, *, text: str, markdown: str) -> str:
        if self.output_format == "text":
            return text or markdown
        return markdown or text

    def should_use_pdf_ocr(self, filename: str, mime: str) -> bool:
        suffix = Path(filename).suffix.lower()
        is_pdf = suffix == ".pdf" or mime == "application/pdf"
        if not is_pdf:
            return False
        if self.preset != "auto":
            return True
        return any(
            getattr(self, field) is not None
            for field in (
                "force_ocr",
                "render_dpi",
                "crop_header_ratio",
                "crop_footer_ratio",
                "trim_margins",
                "remove_repeated_lines",
                "watermark_detection",
                "enable_formula_recognition",
                "pdf_page_chunk_size",
            )
        )

    def to_pipeline_options(self) -> OCRPipelineOptions:
        options = _preset_defaults(self.preset)
        if self.force_ocr is not None:
            options.force_ocr = self.force_ocr
        if self.render_dpi is not None:
            options.render_dpi = self.render_dpi
        if self.crop_header_ratio is not None:
            options.crop_header_ratio = self.crop_header_ratio
        if self.crop_footer_ratio is not None:
            options.crop_footer_ratio = self.crop_footer_ratio
        if self.trim_margins is not None:
            options.trim_margins = self.trim_margins
        if self.remove_repeated_lines is not None:
            options.remove_repeated_lines = self.remove_repeated_lines
        if self.watermark_detection is not None:
            options.watermark_detection = self.watermark_detection
        if self.enable_formula_recognition is not None:
            options.enable_formula_recognition = self.enable_formula_recognition
        if self.pdf_page_chunk_size is not None:
            options.page_chunk_size = self.pdf_page_chunk_size
        if self.preset != "auto" or any(
            value is not None
            for value in (
                self.render_dpi,
                self.crop_header_ratio,
                self.crop_footer_ratio,
                self.trim_margins,
                self.remove_repeated_lines,
                self.watermark_detection,
                self.enable_formula_recognition,
                self.pdf_page_chunk_size,
            )
        ):
            options.force_ocr = True
        return options

    def resolved_summary(self) -> dict[str, Any]:
        pipeline_options = self.to_pipeline_options()
        summary = asdict(pipeline_options)
        summary["preset"] = self.preset
        summary["output_format"] = self.output_format
        summary["cache_key"] = self.cache_key()
        return summary

    def _parse_behavior_dump(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True, exclude={"output_format"})


def _preset_defaults(preset: ParsePreset) -> OCRPipelineOptions:
    if preset == "fast":
        return OCRPipelineOptions(
            force_ocr=True,
            render_dpi=150,
            trim_margins=False,
            remove_repeated_lines=True,
            watermark_detection=False,
            enable_formula_recognition=False,
        )
    if preset == "balanced":
        return OCRPipelineOptions(
            force_ocr=True,
            render_dpi=220,
            trim_margins=True,
            remove_repeated_lines=True,
            watermark_detection=False,
            enable_formula_recognition=False,
        )
    if preset == "accurate":
        return OCRPipelineOptions(
            force_ocr=True,
            render_dpi=280,
            trim_margins=True,
            remove_repeated_lines=True,
            watermark_detection=True,
            enable_formula_recognition=False,
        )
    if preset == "formula":
        return OCRPipelineOptions(
            force_ocr=True,
            render_dpi=280,
            trim_margins=True,
            remove_repeated_lines=True,
            watermark_detection=False,
            enable_formula_recognition=True,
        )
    return OCRPipelineOptions(force_ocr=False)
