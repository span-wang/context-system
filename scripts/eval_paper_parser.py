from __future__ import annotations

import argparse
import json
from itertools import zip_longest
from pathlib import Path
from typing import Any

from paper_dataset_common import (
    build_prediction_from_text,
    flatten_questions,
    normalize_lines,
    normalize_options,
    normalize_text,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate current paper parser output against gold dataset samples.",
    )
    parser.add_argument(
        "dataset_root",
        nargs="?",
        default="data/paper_parser_dataset",
        help="Dataset root or a single sample directory.",
    )
    parser.add_argument(
        "--report-json",
        default="",
        help="Optional path used to write the full evaluation report as JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset_root = Path(args.dataset_root).resolve()
    sample_dirs = _collect_sample_dirs(dataset_root)
    if not sample_dirs:
        print(f"No dataset samples found under {dataset_root}")
        return 1

    report_samples: list[dict[str, Any]] = []
    totals = _new_totals()

    for sample_dir in sample_dirs:
        gold_path = sample_dir / "gold.json"
        source_path = sample_dir / "source.txt"
        if not gold_path.exists() or not source_path.exists():
            continue

        source_text = source_path.read_text(encoding="utf-8")
        gold = json.loads(gold_path.read_text(encoding="utf-8"))
        prediction = build_prediction_from_text(source_text)
        sample_report = _compare_documents(sample_dir.name, gold, prediction)
        report_samples.append(sample_report)
        _accumulate_totals(totals, sample_report)

    if not report_samples:
        print(f"No evaluable samples found under {dataset_root}. Each sample needs source.txt and gold.json.")
        return 1

    summary = _build_summary(totals, len(report_samples))
    print(_format_summary(summary))

    for sample in report_samples:
        mismatch_count = len(sample["mismatches"])
        if mismatch_count <= 0:
            continue
        print(
            f"- {sample['sample_name']}: gold_questions={sample['gold_question_count']} "
            f"predicted_questions={sample['predicted_question_count']} mismatches={mismatch_count}"
        )
        for mismatch in sample["mismatches"][:5]:
            print(f"  * {mismatch}")

    if args.report_json:
        report_path = Path(args.report_json).resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "summary": summary,
                    "samples": report_samples,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"report_json={report_path}")

    return 0


def _collect_sample_dirs(path: Path) -> list[Path]:
    if not path.exists():
        return []
    if (path / "source.txt").exists():
        return [path]
    return sorted(candidate for candidate in path.iterdir() if candidate.is_dir())


def _compare_documents(sample_name: str, gold: dict[str, Any], prediction: dict[str, Any]) -> dict[str, Any]:
    gold_sections = [section for section in gold.get("sections") or [] if isinstance(section, dict)]
    predicted_sections = [section for section in prediction.get("sections") or [] if isinstance(section, dict)]
    gold_questions = flatten_questions({"sections": gold_sections})
    predicted_questions = flatten_questions({"sections": predicted_sections})

    mismatches: list[str] = []
    counts = _new_counts()
    counts["gold_section_count"] = len(gold_sections)
    counts["predicted_section_count"] = len(predicted_sections)
    counts["gold_question_count"] = len(gold_questions)
    counts["predicted_question_count"] = len(predicted_questions)

    for index, pair in enumerate(zip_longest(gold_sections, predicted_sections), start=1):
        gold_section, predicted_section = pair
        if gold_section is None or predicted_section is None:
            mismatches.append(
                f"section[{index}] count mismatch: gold={_section_brief(gold_section)} predicted={_section_brief(predicted_section)}"
            )
            continue
        counts["aligned_section_count"] += 1
        gold_title = normalize_text(str(gold_section.get("title") or ""))
        predicted_title = normalize_text(str(predicted_section.get("title") or ""))
        if gold_title == predicted_title:
            counts["section_title_match_count"] += 1
        else:
            mismatches.append(f"section[{index}] title mismatch: gold={gold_title!r} predicted={predicted_title!r}")

        gold_type = normalize_text(str(gold_section.get("section_type") or ""))
        predicted_type = normalize_text(str(predicted_section.get("section_type") or ""))
        if gold_type == predicted_type:
            counts["section_type_match_count"] += 1
        else:
            mismatches.append(f"section[{index}] type mismatch: gold={gold_type!r} predicted={predicted_type!r}")

        gold_question_count = len(gold_section.get("questions") or [])
        predicted_question_count = len(predicted_section.get("questions") or [])
        if gold_question_count == predicted_question_count:
            counts["section_question_count_match_count"] += 1
        else:
            mismatches.append(
                f"section[{index}] question_count mismatch: gold={gold_question_count} predicted={predicted_question_count}"
            )

    for index, pair in enumerate(zip_longest(gold_questions, predicted_questions), start=1):
        gold_question, predicted_question = pair
        if gold_question is None or predicted_question is None:
            mismatches.append(
                f"question[{index}] count mismatch: gold={_question_brief(gold_question)} predicted={_question_brief(predicted_question)}"
            )
            continue

        counts["aligned_question_count"] += 1
        _compare_field(
            counts,
            mismatches,
            index,
            "question_no",
            gold_question.get("question_no"),
            predicted_question.get("question_no"),
        )
        _compare_field(
            counts,
            mismatches,
            index,
            "question_type",
            gold_question.get("question_type"),
            predicted_question.get("question_type"),
        )
        _compare_field(
            counts,
            mismatches,
            index,
            "stem_text",
            gold_question.get("stem_text"),
            predicted_question.get("stem_text"),
            multiline=True,
        )
        _compare_options_field(
            counts,
            mismatches,
            index,
            gold_question.get("options"),
            predicted_question.get("options"),
        )
        _compare_field(
            counts,
            mismatches,
            index,
            "answer_text",
            gold_question.get("answer_text"),
            predicted_question.get("answer_text"),
            multiline=True,
        )
        _compare_field(
            counts,
            mismatches,
            index,
            "analysis_text",
            gold_question.get("analysis_text"),
            predicted_question.get("analysis_text"),
            multiline=True,
        )

    return {
        "sample_name": sample_name,
        "gold_section_count": counts["gold_section_count"],
        "predicted_section_count": counts["predicted_section_count"],
        "gold_question_count": counts["gold_question_count"],
        "predicted_question_count": counts["predicted_question_count"],
        "metrics": _metrics_from_counts(counts),
        "mismatches": mismatches[:50],
    }


def _new_counts() -> dict[str, int]:
    return {
        "gold_section_count": 0,
        "predicted_section_count": 0,
        "aligned_section_count": 0,
        "section_title_match_count": 0,
        "section_type_match_count": 0,
        "section_question_count_match_count": 0,
        "gold_question_count": 0,
        "predicted_question_count": 0,
        "aligned_question_count": 0,
        "question_no_match_count": 0,
        "question_type_match_count": 0,
        "stem_text_match_count": 0,
        "options_match_count": 0,
        "answer_text_match_count": 0,
        "analysis_text_match_count": 0,
    }


def _new_totals() -> dict[str, int]:
    return _new_counts()


def _accumulate_totals(totals: dict[str, int], sample_report: dict[str, Any]) -> None:
    metrics_source = sample_report["metrics"]["_counts"]
    for key, value in metrics_source.items():
        totals[key] += int(value)


def _build_summary(totals: dict[str, int], sample_count: int) -> dict[str, Any]:
    metrics = _metrics_from_counts(totals)
    metrics.pop("_counts", None)
    return {"sample_count": sample_count, **metrics}


def _metrics_from_counts(counts: dict[str, int]) -> dict[str, Any]:
    aligned_sections = counts["aligned_section_count"]
    aligned_questions = counts["aligned_question_count"]
    return {
        "gold_section_count": counts["gold_section_count"],
        "predicted_section_count": counts["predicted_section_count"],
        "gold_question_count": counts["gold_question_count"],
        "predicted_question_count": counts["predicted_question_count"],
        "section_title_accuracy": _safe_rate(counts["section_title_match_count"], aligned_sections),
        "section_type_accuracy": _safe_rate(counts["section_type_match_count"], aligned_sections),
        "section_question_count_accuracy": _safe_rate(counts["section_question_count_match_count"], aligned_sections),
        "question_no_accuracy": _safe_rate(counts["question_no_match_count"], aligned_questions),
        "question_type_accuracy": _safe_rate(counts["question_type_match_count"], aligned_questions),
        "stem_text_accuracy": _safe_rate(counts["stem_text_match_count"], aligned_questions),
        "options_accuracy": _safe_rate(counts["options_match_count"], aligned_questions),
        "answer_text_accuracy": _safe_rate(counts["answer_text_match_count"], aligned_questions),
        "analysis_text_accuracy": _safe_rate(counts["analysis_text_match_count"], aligned_questions),
        "_counts": counts,
    }


def _compare_field(
    counts: dict[str, int],
    mismatches: list[str],
    index: int,
    field_name: str,
    gold_value: object,
    predicted_value: object,
    *,
    multiline: bool = False,
) -> None:
    normalized_gold = normalize_lines(str(gold_value or "")) if multiline else normalize_text(str(gold_value or ""))
    normalized_predicted = (
        normalize_lines(str(predicted_value or "")) if multiline else normalize_text(str(predicted_value or ""))
    )
    counter_key = f"{field_name}_match_count"
    if normalized_gold == normalized_predicted:
        counts[counter_key] += 1
        return
    mismatches.append(
        f"question[{index}] {field_name} mismatch: gold={normalized_gold[:80]!r} predicted={normalized_predicted[:80]!r}"
    )


def _compare_options_field(
    counts: dict[str, int],
    mismatches: list[str],
    index: int,
    gold_value: object,
    predicted_value: object,
) -> None:
    normalized_gold = normalize_options(gold_value if isinstance(gold_value, list) else [])
    normalized_predicted = normalize_options(predicted_value if isinstance(predicted_value, list) else [])
    if normalized_gold == normalized_predicted:
        counts["options_match_count"] += 1
        return
    mismatches.append(
        f"question[{index}] options mismatch: gold={normalized_gold[:4]!r} predicted={normalized_predicted[:4]!r}"
    )


def _safe_rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _section_brief(value: dict[str, Any] | None) -> str:
    if value is None:
        return "missing"
    return f"{value.get('title') or '-'}:{value.get('section_type') or '-'}"


def _question_brief(value: dict[str, Any] | None) -> str:
    if value is None:
        return "missing"
    return f"{value.get('section_title') or '-'}#{value.get('question_no') or '-'}"


def _format_summary(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"sample_count={summary['sample_count']}",
            f"gold_sections={summary['gold_section_count']} predicted_sections={summary['predicted_section_count']}",
            f"gold_questions={summary['gold_question_count']} predicted_questions={summary['predicted_question_count']}",
            f"section_title_accuracy={summary['section_title_accuracy']}",
            f"section_type_accuracy={summary['section_type_accuracy']}",
            f"section_question_count_accuracy={summary['section_question_count_accuracy']}",
            f"question_no_accuracy={summary['question_no_accuracy']}",
            f"question_type_accuracy={summary['question_type_accuracy']}",
            f"stem_text_accuracy={summary['stem_text_accuracy']}",
            f"options_accuracy={summary['options_accuracy']}",
            f"answer_text_accuracy={summary['answer_text_accuracy']}",
            f"analysis_text_accuracy={summary['analysis_text_accuracy']}",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
