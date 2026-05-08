from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def get_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_api_root() -> Path:
    return get_repo_root() / "apps" / "api"


def bootstrap_api_path() -> Path:
    api_root = get_api_root()
    api_root_text = str(api_root)
    if api_root_text not in sys.path:
        sys.path.insert(0, api_root_text)
    return api_root


def normalize_text(value: str | None) -> str:
    bootstrap_api_path()
    from app.services.paper_dataset import normalize_text as _normalize_text

    return _normalize_text(value)


def normalize_lines(value: str | None) -> str:
    bootstrap_api_path()
    from app.services.paper_dataset import normalize_lines as _normalize_lines

    return _normalize_lines(value)


def normalize_options(options: list[str] | None) -> list[str]:
    bootstrap_api_path()
    from app.services.paper_dataset import normalize_options as _normalize_options

    return _normalize_options(options)


def safe_name(value: str, fallback: str) -> str:
    bootstrap_api_path()
    from app.services.paper_dataset import safe_name as _safe_name

    return _safe_name(value, fallback)


def build_prediction_from_text(text: str) -> dict[str, Any]:
    bootstrap_api_path()
    from app.services.paper_dataset import build_paper_parser_prediction

    return build_paper_parser_prediction(text)


def flatten_questions(document: dict[str, Any]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for section_index, section in enumerate(document.get("sections") or [], start=1):
        section_title = str(section.get("title") or "")
        section_type = str(section.get("section_type") or "")
        for question_index, question in enumerate(section.get("questions") or [], start=1):
            flattened.append(
                {
                    "section_index": section_index,
                    "section_title": section_title,
                    "section_type": section_type,
                    "question_index": question_index,
                    "question_no": str(question.get("question_no") or ""),
                    "question_type": str(question.get("question_type") or ""),
                    "stem_text": normalize_lines(str(question.get("stem_text") or "")),
                    "options": normalize_options(question.get("options") or []),
                    "answer_text": normalize_lines(str(question.get("answer_text") or "")),
                    "analysis_text": normalize_lines(str(question.get("analysis_text") or "")),
                }
            )
    return flattened
