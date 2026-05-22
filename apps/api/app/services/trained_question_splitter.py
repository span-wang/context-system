from __future__ import annotations

import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any

from app.core.config import get_settings


QUESTION_SPLITTER_ARTIFACT_TYPE = "question_start_naive_bayes_v1"
_QUESTION_START_PATTERN = re.compile(r"^\s*(?:#+\s*)?(?:第\s*)?(?:[0-9]{1,3}|[一二三四五六七八九十百]{1,6})\s*(?:题|[\.、．)])\s*")
_SECTION_HEADER_PATTERN = re.compile(
    r"^\s*(?:#+\s*)?(?:(?:第\s*[一二三四五六七八九十百0-9]+\s*部分)|(?:[一二三四五六七八九十百0-9]+\s*[、.．]))?\s*"
    r"(?:单项选择题|多项选择题|不定项选择题|判断题|填空题|简答题|计算题|案例分析题|综合题|材料分析题)"
)
_OPTION_LINE_PATTERN = re.compile(r"^\s*[A-H][\.\、．)]\s*")
_ANSWER_LINE_PATTERN = re.compile(r"^\s*(?:#+\s*)?(?:答案|参考答案|正确答案)\s*[:：]")
_ANALYSIS_LINE_PATTERN = re.compile(r"^\s*(?:#+\s*)?(?:解析|答案解析|【解析】)\s*(?:[:：]|\s*$)")
_ACTIVE_ARTIFACT_CACHE: dict[str, Any] = {"checked_at": 0.0, "latest_mtime": None, "artifact_path": "", "artifact_mtime": None, "artifact": None}


def train_question_splitter_artifact(samples: list[dict[str, Any]], *, model_id: str, created_at: str) -> dict[str, Any]:
    rows = _build_labeled_rows(samples)
    model = _train_binary_feature_model(rows)
    metrics = _evaluate_rows(rows, model)
    return {
        "artifact_type": QUESTION_SPLITTER_ARTIFACT_TYPE,
        "model_id": model_id,
        "created_at": created_at,
        "labels": ["other", "question_start"],
        "line_count": len(rows),
        "question_start_line_count": sum(1 for row in rows if row["label"] == "question_start"),
        "other_line_count": sum(1 for row in rows if row["label"] == "other"),
        "model": model,
        "metrics": metrics,
    }


def score_question_start_line(line: str) -> float:
    artifact = load_active_question_splitter_artifact()
    if not _is_supported_artifact(artifact):
        return 0.0
    return predict_question_start_probability(line, artifact)


def predict_question_start_probability(line: str, artifact: dict[str, Any]) -> float:
    start_score = _score_line_label(line, artifact, "question_start")
    other_score = _score_line_label(line, artifact, "other")
    delta = max(-50.0, min(50.0, start_score - other_score))
    return 1.0 / (1.0 + math.exp(-delta))


def load_active_question_splitter_artifact() -> dict[str, Any] | None:
    latest_path = _model_registry_root() / "latest.json"
    now = time.time()
    if now - float(_ACTIVE_ARTIFACT_CACHE.get("checked_at") or 0.0) < 3:
        return _ACTIVE_ARTIFACT_CACHE.get("artifact")
    _ACTIVE_ARTIFACT_CACHE["checked_at"] = now
    if not latest_path.exists():
        _ACTIVE_ARTIFACT_CACHE.update({"latest_mtime": None, "artifact_path": "", "artifact_mtime": None, "artifact": None})
        return None
    latest_mtime = latest_path.stat().st_mtime
    latest = _read_json(latest_path)
    artifact_path = Path(str(latest.get("artifact_path") or ""))
    if not artifact_path.exists():
        _ACTIVE_ARTIFACT_CACHE.update({"latest_mtime": latest_mtime, "artifact_path": str(artifact_path), "artifact_mtime": None, "artifact": None})
        return None
    artifact_mtime = artifact_path.stat().st_mtime
    if (
        _ACTIVE_ARTIFACT_CACHE.get("latest_mtime") == latest_mtime
        and _ACTIVE_ARTIFACT_CACHE.get("artifact_path") == str(artifact_path)
        and _ACTIVE_ARTIFACT_CACHE.get("artifact_mtime") == artifact_mtime
    ):
        return _ACTIVE_ARTIFACT_CACHE.get("artifact")
    artifact = _read_json(artifact_path)
    if not _is_supported_artifact(artifact):
        artifact = None
    _ACTIVE_ARTIFACT_CACHE.update(
        {
            "latest_mtime": latest_mtime,
            "artifact_path": str(artifact_path),
            "artifact_mtime": artifact_mtime,
            "artifact": artifact,
        }
    )
    return artifact


def _build_labeled_rows(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sample in samples:
        text = str(sample.get("input") or "")
        target = sample.get("target") if isinstance(sample.get("target"), dict) else {}
        if not text.strip() or not target:
            continue
        target_starts = _target_question_start_keys(target)
        for line in _split_lines(text):
            line_key = _question_start_key(line)
            label = "question_start" if line_key and line_key in target_starts else "other"
            rows.append({"text": line, "label": label, "features": sorted(_line_features(line))})
    return rows


def _target_question_start_keys(target: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for section in target.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for question in section.get("questions") or []:
            if not isinstance(question, dict):
                continue
            no = str(question.get("question_no") or "").strip()
            stem = str(question.get("stem_text") or "").strip()
            if not no:
                continue
            keys.add(_normalize_key(f"{no}:{stem[:32]}"))
            keys.add(_normalize_key(no))
    return keys


def _question_start_key(line: str) -> str:
    match = _QUESTION_START_PATTERN.match(line.strip())
    if match is None:
        return ""
    no_match = re.match(r"^\s*(?:#+\s*)?(?:第\s*)?([0-9]{1,3}|[一二三四五六七八九十百]{1,6})", line.strip())
    if no_match is None:
        return ""
    no = no_match.group(1)
    body = line[match.end() :].strip()
    return _normalize_key(f"{no}:{body[:32]}") if body else _normalize_key(no)


def _train_binary_feature_model(rows: list[dict[str, Any]]) -> dict[str, Any]:
    labels = ["other", "question_start"]
    label_counts = {label: 0 for label in labels}
    feature_counts: dict[str, dict[str, int]] = {}
    for row in rows:
        label = str(row.get("label") or "")
        if label not in label_counts:
            continue
        label_counts[label] += 1
        for feature in row.get("features") or []:
            feature_counts.setdefault(str(feature), {item: 0 for item in labels})[label] += 1
    return {
        "labels": labels,
        "label_counts": label_counts,
        "feature_counts": feature_counts,
        "threshold": 0.55,
    }


def _evaluate_rows(rows: list[dict[str, Any]], model: dict[str, Any]) -> dict[str, Any]:
    artifact = {"artifact_type": QUESTION_SPLITTER_ARTIFACT_TYPE, "model": model}
    threshold = float(model.get("threshold") or 0.55)
    tp = fp = tn = fn = 0
    for row in rows:
        predicted_start = predict_question_start_probability(str(row.get("text") or ""), artifact) >= threshold
        actual_start = row.get("label") == "question_start"
        if predicted_start and actual_start:
            tp += 1
        elif predicted_start and not actual_start:
            fp += 1
        elif not predicted_start and actual_start:
            fn += 1
        else:
            tn += 1
    total = tp + fp + tn + fn
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)
    return {
        "line_count": total,
        "accuracy": round((tp + tn) / max(total, 1), 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "false_positive": fp,
        "false_negative": fn,
    }


def _score_line_label(line: str, artifact: dict[str, Any], label: str) -> float:
    model = artifact.get("model") if isinstance(artifact.get("model"), dict) else {}
    label_counts = model.get("label_counts") if isinstance(model.get("label_counts"), dict) else {}
    feature_counts = model.get("feature_counts") if isinstance(model.get("feature_counts"), dict) else {}
    labels = [str(item) for item in model.get("labels") or ["other", "question_start"]]
    total = sum(int(label_counts.get(item, 0) or 0) for item in labels)
    label_count = int(label_counts.get(label, 0) or 0)
    score = math.log((label_count + 1) / (total + len(labels)))
    for feature in _line_features(line):
        per_label = feature_counts.get(feature) if isinstance(feature_counts.get(feature), dict) else {}
        feature_count = int(per_label.get(label, 0) or 0)
        score += math.log((feature_count + 1) / (label_count + 2))
    return score


def _line_features(line: str) -> set[str]:
    text = re.sub(r"\s+", " ", str(line or "").strip())
    compact = re.sub(r"\s+", "", text)
    features: set[str] = set()
    if not text:
        return {"empty"}
    features.add(f"len:{_bucket(len(compact), (4, 8, 16, 32, 64, 120))}")
    if _QUESTION_START_PATTERN.match(text):
        features.add("regex_question_start")
    if _SECTION_HEADER_PATTERN.match(text):
        features.add("section_header")
    if _OPTION_LINE_PATTERN.match(text):
        features.add("option_line")
    if _ANSWER_LINE_PATTERN.match(text):
        features.add("answer_line")
    if _ANALYSIS_LINE_PATTERN.match(text):
        features.add("analysis_line")
    if len(re.findall(r"[A-H][\.\、．)]", text)) >= 2:
        features.add("dense_options")
    if "（）" in text or "()" in text or "()" in compact:
        features.add("blank_slot")
    if any(token in text for token in ("下列", "正确", "计算", "根据", "关于", "表述")):
        features.add("question_prompt_word")
    if any(token in text for token in ("资料", "要求", "回答下列", "根据上述")):
        features.add("shared_context_word")
    if re.fullmatch(r"\d{1,3}", compact):
        features.add("digits_only")
    return features


def _bucket(value: int, boundaries: tuple[int, ...]) -> str:
    for boundary in boundaries:
        if value <= boundary:
            return f"<= {boundary}"
    return f"> {boundaries[-1]}"


def _split_lines(text: str) -> list[str]:
    return [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").splitlines() if line.strip()]


def _normalize_key(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def _is_supported_artifact(artifact: dict[str, Any] | None) -> bool:
    return bool(isinstance(artifact, dict) and artifact.get("artifact_type") == QUESTION_SPLITTER_ARTIFACT_TYPE and isinstance(artifact.get("model"), dict))


def _model_registry_root() -> Path:
    try:
        return get_settings().storage.root_path / "models" / "question_splitter"
    except Exception:
        root = Path(os.getenv("STORAGE_ROOT") or "data")
        return root / "models" / "question_splitter"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}
