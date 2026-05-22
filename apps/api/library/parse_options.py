from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from library.pdf_ocr_pipeline import OCRPipelineOptions


ParsePreset = Literal["vl15", "v3"]
ParseOutputFormat = Literal["markdown", "text"]

DEFAULT_PARSE_PRESET: ParsePreset = "vl15"
DEFAULT_PARSE_OUTPUT_FORMAT: ParseOutputFormat = "markdown"
DEFAULT_PARSE_PAGE_CHUNK_SIZE = 4

PARSE_PRESET_ORDER: tuple[ParsePreset, ...] = ("vl15", "v3")
PRIMARY_PARSE_PRESETS: tuple[ParsePreset, ...] = ("vl15", "v3")
PARSE_OUTPUT_FORMAT_LABELS: dict[ParseOutputFormat, str] = {
    "markdown": "Markdown",
    "text": "TXT",
}
LEGACY_PARSE_PRESET_OVERRIDES: dict[str, dict[str, Any]] = {
    "accurate": {
        "preset": "v3",
        "render_dpi": 320,
        "trim_margins": True,
        "remove_repeated_lines": True,
        "watermark_detection": True,
        "enable_formula_recognition": False,
    },
    "formula": {
        "preset": "v3",
        "render_dpi": 340,
        "trim_margins": True,
        "remove_repeated_lines": True,
        "watermark_detection": False,
        "enable_formula_recognition": True,
    },
    "v5": {
        "preset": "v3",
        "render_dpi": 320,
        "trim_margins": True,
        "remove_repeated_lines": True,
        "watermark_detection": False,
        "enable_formula_recognition": False,
    },
    "balanced": {
        "preset": "v3",
        "render_dpi": 220,
        "trim_margins": True,
        "remove_repeated_lines": True,
        "watermark_detection": False,
        "enable_formula_recognition": False,
    },
    "fast": {
        "preset": "v3",
        "render_dpi": 150,
        "trim_margins": False,
        "remove_repeated_lines": True,
        "watermark_detection": False,
        "enable_formula_recognition": False,
    },
    "auto": {
        "preset": "v3",
        "render_dpi": 240,
        "trim_margins": True,
        "remove_repeated_lines": True,
        "watermark_detection": True,
        "enable_formula_recognition": False,
    },
}
PARSE_PRESET_DEFINITIONS: dict[ParsePreset, dict[str, Any]] = {
    "vl15": {
        "value": "vl15",
        "label": "VL1.5",
        "short_label": "VL1.5",
        "engine": "PaddleOCR-VL1.5",
        "description": "多模态整卷解析，适合复杂图文混排 PDF 和整卷重组输出。",
        "dpi_hint": "240",
        "primary": True,
        "defaults": {
            "render_dpi": 240,
            "trim_margins": True,
            "remove_repeated_lines": False,
            "watermark_detection": False,
            "enable_formula_recognition": False,
        },
    },
    "v3": {
        "value": "v3",
        "label": "V3",
        "short_label": "V3",
        "engine": "PP-StructureV3",
        "description": "结构化版面解析，适合表格、题号分区和复杂布局页。",
        "dpi_hint": "320",
        "primary": True,
        "defaults": {
            "render_dpi": 320,
            "trim_margins": True,
            "remove_repeated_lines": True,
            "watermark_detection": True,
            "enable_formula_recognition": False,
        },
    },
}


class DocumentParseOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset: ParsePreset = DEFAULT_PARSE_PRESET
    output_format: ParseOutputFormat = DEFAULT_PARSE_OUTPUT_FORMAT
    raw_ocr_mode: bool | None = None
    preserve_pdf_image_content: bool | None = None
    force_ocr: bool | None = True
    render_dpi: int | None = Field(default=None, ge=96, le=360)
    crop_header_ratio: float | None = Field(default=None, ge=0.0, le=0.2)
    crop_footer_ratio: float | None = Field(default=None, ge=0.0, le=0.2)
    trim_margins: bool | None = None
    remove_repeated_lines: bool | None = None
    watermark_detection: bool | None = None
    enable_formula_recognition: bool | None = None
    pdf_page_chunk_size: int | None = Field(default=None, ge=1, le=50)

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_presets(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        raw_preset = str(data.get("preset") or "").strip()
        overrides = LEGACY_PARSE_PRESET_OVERRIDES.get(raw_preset)
        if overrides is None:
            return data
        normalized = dict(data)
        normalized["preset"] = overrides["preset"]
        for key, value in overrides.items():
            if key == "preset":
                continue
            normalized.setdefault(key, value)
        return normalized

    def should_use_layout_pipeline(self) -> bool:
        return self.preset == "v3"

    def should_use_vl15_pipeline(self) -> bool:
        return self.preset == "vl15"

    def is_default(self) -> bool:
        return self._parse_behavior_dump() == {"preset": DEFAULT_PARSE_PRESET, "force_ocr": True}

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
        return is_pdf

    def use_raw_ocr_mode(self) -> bool:
        return bool(self.raw_ocr_mode)

    def should_preserve_pdf_image_content(self) -> bool:
        if self.preserve_pdf_image_content is None:
            return True
        return bool(self.preserve_pdf_image_content)

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
        if self.use_raw_ocr_mode():
            options.remove_repeated_lines = False
        options.force_ocr = True
        return options

    def resolved_summary(self) -> dict[str, Any]:
        pipeline_options = self.to_pipeline_options()
        summary = asdict(pipeline_options)
        summary["preset"] = self.preset
        summary["output_format"] = self.output_format
        summary["cache_key"] = self.cache_key()
        if self.raw_ocr_mode is not None:
            summary["raw_ocr_mode"] = bool(self.raw_ocr_mode)
        if self.preserve_pdf_image_content is not None:
            summary["preserve_pdf_image_content"] = bool(self.preserve_pdf_image_content)
        return summary

    def _parse_behavior_dump(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True, exclude={"output_format"})


def _preset_defaults(preset: ParsePreset) -> OCRPipelineOptions:
    defaults = get_parse_preset_definition(preset)["defaults"]
    return OCRPipelineOptions(
        force_ocr=True,
        render_dpi=int(defaults["render_dpi"]),
        trim_margins=bool(defaults["trim_margins"]),
        remove_repeated_lines=bool(defaults["remove_repeated_lines"]),
        watermark_detection=bool(defaults["watermark_detection"]),
        enable_formula_recognition=bool(defaults["enable_formula_recognition"]),
    )


def get_parse_preset_definition(preset: ParsePreset) -> dict[str, Any]:
    return dict(PARSE_PRESET_DEFINITIONS[preset])


def list_parse_preset_definitions(*, primary_only: bool = False) -> list[dict[str, Any]]:
    allowed = set(PRIMARY_PARSE_PRESETS) if primary_only else None
    definitions: list[dict[str, Any]] = []
    for preset in PARSE_PRESET_ORDER:
        if allowed is not None and preset not in allowed:
            continue
        definition = get_parse_preset_definition(preset)
        definition["defaults"] = dict(definition["defaults"])
        definitions.append(definition)
    return definitions


def get_parse_capability_payload() -> dict[str, Any]:
    return {
        "default_preset": DEFAULT_PARSE_PRESET,
        "default_output_format": DEFAULT_PARSE_OUTPUT_FORMAT,
        "force_ocr_locked": True,
        "default_page_chunk_size": DEFAULT_PARSE_PAGE_CHUNK_SIZE,
        "presets": list_parse_preset_definitions(),
        "output_formats": [
            {"value": value, "label": label}
            for value, label in PARSE_OUTPUT_FORMAT_LABELS.items()
        ],
    }


def build_document_parse_options(
    *,
    preset: ParsePreset = DEFAULT_PARSE_PRESET,
    output_format: ParseOutputFormat = DEFAULT_PARSE_OUTPUT_FORMAT,
    raw_ocr_mode: bool | None = None,
    preserve_pdf_image_content: bool | None = None,
    force_ocr: bool | None = None,
    render_dpi: int | None = None,
    crop_header_ratio: float | None = None,
    crop_footer_ratio: float | None = None,
    trim_margins: bool | None = None,
    remove_repeated_lines: bool | None = None,
    watermark_detection: bool | None = None,
    enable_formula_recognition: bool | None = None,
    pdf_page_chunk_size: int | None = None,
) -> DocumentParseOptions:
    return DocumentParseOptions(
        preset=preset,
        output_format=output_format,
        raw_ocr_mode=raw_ocr_mode,
        preserve_pdf_image_content=preserve_pdf_image_content,
        force_ocr=True,
        render_dpi=render_dpi,
        crop_header_ratio=crop_header_ratio,
        crop_footer_ratio=crop_footer_ratio,
        trim_margins=trim_margins,
        remove_repeated_lines=remove_repeated_lines,
        watermark_detection=watermark_detection,
        enable_formula_recognition=enable_formula_recognition,
        pdf_page_chunk_size=pdf_page_chunk_size,
    )
