from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from library.parser import ParsedDocument, ParsedPage


PAPER_DATASET_AUTO_EXPORT_ENV = "PAPER_DATASET_AUTO_EXPORT"
PAPER_DATASET_ROOT_ENV = "PAPER_DATASET_ROOT"
PAPER_DATASET_AUTO_INIT_GOLD_ENV = "PAPER_DATASET_AUTO_INIT_GOLD"
PAPER_DATASET_INCLUDE_SOURCE_ENV = "PAPER_DATASET_INCLUDE_SOURCE"
_PENDING_LABEL_STATUSES = {"", "draft", "pending", "todo"}


@dataclass(slots=True)
class PaperDatasetSyncSource:
    sample_dir: Path
    source_file: str
    label_status: str | None
    meta: dict[str, Any]
    document: dict[str, Any]
    used_gold: bool


def should_auto_export_paper_dataset() -> bool:
    return _env_bool(PAPER_DATASET_AUTO_EXPORT_ENV, True)


def resolve_paper_dataset_root() -> Path:
    raw_root = os.getenv(PAPER_DATASET_ROOT_ENV)
    if raw_root and raw_root.strip():
        candidate = Path(raw_root.strip())
        if not candidate.is_absolute():
            candidate = get_settings().storage.root_path / candidate
    else:
        candidate = get_settings().storage.root_path / "paper_parser_dataset"
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def normalize_lines(value: str | None) -> str:
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def normalize_options(options: list[str] | None) -> list[str]:
    return [normalize_text(option) for option in (options or []) if normalize_text(option)]


def safe_name(value: str, fallback: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z._-]+", "_", value).strip("._-")
    return normalized or fallback


def is_pending_label_status(status: str | None) -> bool:
    normalized = str(status or "").strip().lower()
    return normalized in _PENDING_LABEL_STATUSES


def build_paper_parser_prediction(text: str) -> dict[str, Any]:
    from app.services.papers import _parse_question_block, _split_paper_sections

    normalized = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n").strip()
    document = ParsedDocument(
        text=normalized,
        markdown=normalized,
        provider="dataset_source_text",
        pages=[ParsedPage(page_number=1, text=normalized, markdown=normalized)],
    )
    sections = _split_paper_sections(document, normalized)
    payload_sections: list[dict[str, Any]] = []
    total_question_count = 0

    for section in sections:
        payload_questions: list[dict[str, Any]] = []
        for order, block in enumerate(section.blocks, start=1):
            parsed = _parse_question_block(block, section)
            payload_questions.append(
                {
                    "order": order,
                    "question_no": parsed.question_no,
                    "question_type": parsed.question_type,
                    "stem_text": normalize_lines(parsed.stem_text),
                    "options": normalize_options(parsed.options_json),
                    "answer_text": normalize_lines(parsed.answer_text),
                    "analysis_text": normalize_lines(parsed.analysis_text),
                    "subquestion_count": parsed.subquestion_count,
                    "quality_score": parsed.quality_score,
                    "quality_issues": parsed.quality_issues,
                }
            )
        total_question_count += len(payload_questions)
        payload_sections.append(
            {
                "title": section.title,
                "section_type": section.section_type,
                "sort_order": section.sort_order,
                "question_count": len(payload_questions),
                "questions": payload_questions,
            }
        )

    return {
        "version": 1,
        "source_format": "parsed_text",
        "section_count": len(payload_sections),
        "question_count": total_question_count,
        "sections": payload_sections,
    }


def build_gold_template(prediction: dict[str, object]) -> dict[str, object]:
    sections_payload: list[dict[str, object]] = []
    for section in prediction.get("sections") or []:
        if not isinstance(section, dict):
            continue
        question_payload: list[dict[str, object]] = []
        for question in section.get("questions") or []:
            if not isinstance(question, dict):
                continue
            question_payload.append(
                {
                    "question_no": question.get("question_no"),
                    "question_type": question.get("question_type"),
                    "stem_text": question.get("stem_text"),
                    "options": question.get("options") or [],
                    "answer_text": question.get("answer_text"),
                    "analysis_text": question.get("analysis_text"),
                }
            )
        sections_payload.append(
            {
                "title": section.get("title"),
                "section_type": section.get("section_type"),
                "questions": question_payload,
            }
        )
    return {
        "version": 1,
        "label_status": "draft",
        "notes": "",
        "sections": sections_payload,
    }


def export_paper_parser_sample(
    *,
    paper_id: int,
    paper_name: str,
    source_text: str,
    markdown_image_roots: list[str] | None = None,
    paper_status: str | None = None,
    paper_review_status: str | None = None,
    exam_year: int | None = None,
    exam_month: int | None = None,
    exam_region: str | None = None,
    paper_type: str | None = None,
    subject_name: str | None = None,
    subject_code: str | None = None,
    category_name: str | None = None,
    asset_id: int | None = None,
    asset_filename: str | None = None,
    asset_mime_type: str | None = None,
    asset_storage_path: str | None = None,
    asset_parse_status: str | None = None,
    asset_ocr_status: str | None = None,
    provider: str | None = None,
    parse_options: dict[str, object] | None = None,
    stored_section_count: int | None = None,
    stored_question_count: int | None = None,
    stored_needs_review_count: int | None = None,
    output_root: Path | None = None,
    init_gold: bool | None = None,
    include_source: bool | None = None,
) -> Path:
    dataset_root = output_root or resolve_paper_dataset_root()
    sample_dir = resolve_paper_dataset_sample_dir(paper_id, paper_name, output_root=dataset_root)
    sample_dir.mkdir(parents=True, exist_ok=True)

    prediction = build_paper_parser_prediction(source_text)
    gold_template = build_gold_template(prediction)
    meta = {
        "version": 1,
        "paper_id": paper_id,
        "paper_name": paper_name,
        "paper_status": paper_status,
        "paper_review_status": paper_review_status,
        "exam_year": exam_year,
        "exam_month": exam_month,
        "exam_region": exam_region,
        "paper_type": paper_type,
        "subject_name": subject_name,
        "subject_code": subject_code,
        "category_name": category_name,
        "asset_id": asset_id,
        "asset_filename": asset_filename,
        "asset_mime_type": asset_mime_type,
        "asset_storage_path": asset_storage_path,
        "asset_parse_status": asset_parse_status,
        "asset_ocr_status": asset_ocr_status,
        "source_text_length": len(source_text),
        "stored_section_count": stored_section_count,
        "stored_question_count": stored_question_count,
        "stored_needs_review_count": stored_needs_review_count,
        "predicted_section_count": prediction["section_count"],
        "predicted_question_count": prediction["question_count"],
        "provider": provider,
        "parse_options": parse_options or {},
        "export_root": str(dataset_root),
    }

    (sample_dir / "source.txt").write_text(source_text, encoding="utf-8")
    (sample_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (sample_dir / "prediction.json").write_text(
        json.dumps(prediction, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (sample_dir / "gold.template.json").write_text(
        json.dumps(gold_template, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    should_init_gold = _env_bool(PAPER_DATASET_AUTO_INIT_GOLD_ENV, True) if init_gold is None else init_gold
    gold_path = sample_dir / "gold.json"
    if should_init_gold and not gold_path.exists():
        gold_path.write_text(json.dumps(gold_template, ensure_ascii=False, indent=2), encoding="utf-8")

    should_include_source = (
        _env_bool(PAPER_DATASET_INCLUDE_SOURCE_ENV, False) if include_source is None else include_source
    )
    if should_include_source and asset_storage_path and asset_filename:
        source_path = _resolve_storage_path(asset_storage_path)
        if source_path.exists():
            raw_dir = sample_dir / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, raw_dir / asset_filename)

    _copy_markdown_images(sample_dir, markdown_image_roots)

    return sample_dir


def find_paper_dataset_sample_dir(
    paper_id: int,
    paper_name: str | None = None,
    *,
    output_root: Path | None = None,
) -> Path | None:
    dataset_root = output_root or resolve_paper_dataset_root()
    preferred = resolve_paper_dataset_sample_dir(paper_id, paper_name or "", output_root=dataset_root)
    if preferred.exists():
        return preferred

    candidates = sorted(
        [path for path in dataset_root.glob(f"paper_{paper_id:06d}_*") if path.is_dir()],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def load_paper_dataset_sync_source(
    paper_id: int,
    paper_name: str | None = None,
    *,
    output_root: Path | None = None,
) -> PaperDatasetSyncSource:
    sample_dir = find_paper_dataset_sample_dir(paper_id, paper_name, output_root=output_root)
    if sample_dir is None:
        raise FileNotFoundError(f"未找到试卷 {paper_id} 对应的训练样本目录")

    meta = _read_json_object(sample_dir / "meta.json")
    gold = _read_json_object(sample_dir / "gold.json")
    prediction = _read_json_object(sample_dir / "prediction.json")
    gold_sections = _extract_sections(gold)
    prediction_sections = _extract_sections(prediction)
    label_status = str(gold.get("label_status") or "").strip() or None

    if gold_sections and not is_pending_label_status(label_status):
        return PaperDatasetSyncSource(
            sample_dir=sample_dir,
            source_file="gold.json",
            label_status=label_status,
            meta=meta,
            document=gold,
            used_gold=True,
        )
    if prediction_sections:
        return PaperDatasetSyncSource(
            sample_dir=sample_dir,
            source_file="prediction.json",
            label_status=label_status,
            meta=meta,
            document=prediction,
            used_gold=False,
        )
    if gold_sections:
        return PaperDatasetSyncSource(
            sample_dir=sample_dir,
            source_file="gold.json",
            label_status=label_status,
            meta=meta,
            document=gold,
            used_gold=True,
        )
    raise ValueError(f"训练样本目录 {sample_dir} 中没有可同步的题目数据")


def resolve_paper_dataset_sample_dir(
    paper_id: int,
    paper_name: str,
    *,
    output_root: Path | None = None,
) -> Path:
    dataset_root = output_root or resolve_paper_dataset_root()
    return dataset_root / f"paper_{paper_id:06d}_{safe_name(paper_name or '', 'paper')}"


def _resolve_storage_path(storage_path: str) -> Path:
    candidate = Path(storage_path)
    if candidate.is_absolute():
        return candidate
    return get_settings().storage.root_path / candidate


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _copy_markdown_images(sample_dir: Path, markdown_image_roots: list[str] | None) -> None:
    roots = [Path(item) for item in (markdown_image_roots or []) if str(item).strip()]
    if not roots:
        return
    imgs_dir = sample_dir / "imgs"
    copied: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        source_root = root / "imgs" if (root / "imgs").exists() else root
        for image_path in source_root.rglob("*"):
            if not image_path.is_file():
                continue
            try:
                relative_path = image_path.relative_to(source_root)
            except ValueError:
                continue
            target_path = imgs_dir / relative_path
            if target_path in copied:
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(image_path, target_path)
            copied.add(target_path)


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _extract_sections(document: dict[str, Any]) -> list[dict[str, Any]]:
    sections = document.get("sections")
    if not isinstance(sections, list):
        return []
    return [section for section in sections if isinstance(section, dict)]
