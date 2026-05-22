from __future__ import annotations

import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any


OCR_LINE_FILTER_ARTIFACT_TYPE = "ocr_line_filter_naive_bayes_v1"
_NOISE_HINTS = ("二维码", "公众号", "微信", "扫一扫", "扫描", "内部资料", "仅供参考", "版权所有")
_PAGE_NUMBER_PATTERN = re.compile(r"^(?:第\s*)?\d+\s*(?:页|頁|/+\s*\d+)?$")
_PAGE_X_OF_Y_PATTERN = re.compile(r"^(?:page\s*)?\d+\s*/\s*\d+$", re.IGNORECASE)
_OPTION_LINE_PATTERN = re.compile(r"^\s*[A-H][\.\、．)]\s*")
_QUESTION_START_PATTERN = re.compile(r"^\s*(?:#+\s*)?(?:第\s*)?(?:\d{1,3}|[一二三四五六七八九十百]{1,6})\s*(?:题|[\.、．)])\s*")
_SECTION_HEADER_PATTERN = re.compile(
    r"^\s*(?:#+\s*)?(?:(?:第\s*[一二三四五六七八九十百0-9]+\s*部分)|(?:[一二三四五六七八九十百0-9]+\s*[、.．]))?\s*"
    r"(?:单项选择题|多项选择题|不定项选择题|判断题|填空题|简答题|计算题|案例分析题|综合题|材料分析题)"
)
_SYMBOL_ONLY_PATTERN = re.compile(r"^[\s\-_=~·•⋅…—–_（）(){}[\]<>【】《》。、，,.:：;；|/\\]+$")

_ACTIVE_ARTIFACT_CACHE: dict[str, Any] = {"checked_at": 0.0, "latest_mtime": None, "artifact_path": "", "artifact_mtime": None, "artifact": None}


def train_ocr_line_filter_artifact(samples: list[dict[str, Any]], *, model_id: str, created_at: str) -> dict[str, Any]:
    rows = _build_labeled_rows(samples)
    model = _train_binary_feature_model(rows)
    metrics = _evaluate_rows(rows, model)
    return {
        "artifact_type": OCR_LINE_FILTER_ARTIFACT_TYPE,
        "model_id": model_id,
        "created_at": created_at,
        "labels": ["keep", "delete"],
        "line_count": len(rows),
        "delete_line_count": sum(1 for row in rows if row["label"] == "delete"),
        "keep_line_count": sum(1 for row in rows if row["label"] == "keep"),
        "model": model,
        "metrics": metrics,
    }


def apply_ocr_line_filter_artifact(text: str, artifact: dict[str, Any]) -> str:
    if not _is_supported_artifact(artifact):
        return text.strip()
    lines = _split_lines(text)
    kept = [line for line in lines if not should_drop_line(line, artifact)]
    return "\n".join(kept).strip()


def should_drop_line(line: str, artifact: dict[str, Any] | None = None) -> bool:
    model_artifact = artifact if artifact is not None else load_active_ocr_line_filter_artifact()
    if not _is_supported_artifact(model_artifact):
        return False
    normalized = _normalize_line(line)
    if not normalized or _is_high_signal_line(normalized):
        return False
    score = score_line_label(normalized, model_artifact, "delete") - score_line_label(normalized, model_artifact, "keep")
    threshold = float(((model_artifact or {}).get("model") or {}).get("threshold") or 0.0)
    return score >= threshold


def score_line_label(line: str, artifact: dict[str, Any], label: str) -> float:
    model = artifact.get("model") if isinstance(artifact.get("model"), dict) else {}
    label_counts = model.get("label_counts") if isinstance(model.get("label_counts"), dict) else {}
    feature_counts = model.get("feature_counts") if isinstance(model.get("feature_counts"), dict) else {}
    labels = [str(item) for item in model.get("labels") or ["keep", "delete"]]
    total = sum(int(label_counts.get(item, 0) or 0) for item in labels)
    label_count = int(label_counts.get(label, 0) or 0)
    score = math.log((label_count + 1) / (total + len(labels)))
    features = _line_features(line)
    for feature in features:
        per_label = feature_counts.get(feature) if isinstance(feature_counts.get(feature), dict) else {}
        feature_count = int(per_label.get(label, 0) or 0)
        score += math.log((feature_count + 1) / (label_count + 2))
    return score


def load_active_ocr_line_filter_artifact() -> dict[str, Any] | None:
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
        input_text = str(sample.get("input") or "")
        target_text = str(sample.get("target") or "")
        if not input_text.strip() or not target_text.strip():
            continue
        target_norm = _normalize_compact(target_text)
        target_lines = [_normalize_compact(line) for line in _split_lines(target_text)]
        for line in _split_lines(input_text):
            normalized_line = _normalize_compact(line)
            if not normalized_line:
                continue
            label = "keep" if _line_is_preserved(normalized_line, target_norm, target_lines) else "delete"
            rows.append({"text": line, "label": label, "features": sorted(_line_features(line))})
    return rows


def _line_is_preserved(line: str, target_text: str, target_lines: list[str]) -> bool:
    if line in target_text:
        return True
    if any(line == target_line for target_line in target_lines):
        return True
    if len(line) >= 12 and any(line in target_line or target_line in line for target_line in target_lines if len(target_line) >= 12):
        return True
    return False


def _train_binary_feature_model(rows: list[dict[str, Any]]) -> dict[str, Any]:
    labels = ["keep", "delete"]
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
        "threshold": 0.0,
    }


def _evaluate_rows(rows: list[dict[str, Any]], model: dict[str, Any]) -> dict[str, Any]:
    artifact = {"artifact_type": OCR_LINE_FILTER_ARTIFACT_TYPE, "model": model}
    tp = fp = tn = fn = 0
    for row in rows:
        predicted_delete = should_drop_line(str(row.get("text") or ""), artifact)
        actual_delete = row.get("label") == "delete"
        if predicted_delete and actual_delete:
            tp += 1
        elif predicted_delete and not actual_delete:
            fp += 1
        elif not predicted_delete and actual_delete:
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


def _line_features(line: str) -> set[str]:
    text = _normalize_line(line)
    compact = re.sub(r"\s+", "", text)
    features: set[str] = set()
    if not text:
        return {"empty"}
    char_count = len(compact)
    features.add(f"len:{_bucket(char_count, (4, 8, 16, 32, 64, 120))}")
    if any(hint in text for hint in _NOISE_HINTS):
        features.add("noise_hint")
    if _PAGE_NUMBER_PATTERN.match(text) or _PAGE_X_OF_Y_PATTERN.match(text):
        features.add("page_number")
    if _SYMBOL_ONLY_PATTERN.match(text):
        features.add("symbol_only")
    if re.search(r"https?://|www\\.", text, re.IGNORECASE):
        features.add("url")
    if "<img" in text.lower() or "imgs/" in text.lower():
        features.add("image_ref")
    if _OPTION_LINE_PATTERN.match(text):
        features.add("option_line")
    if _QUESTION_START_PATTERN.match(text):
        features.add("question_start")
    if _SECTION_HEADER_PATTERN.match(text):
        features.add("section_header")
    if "答案" in text:
        features.add("answer_marker")
    if "解析" in text:
        features.add("analysis_marker")
    if re.fullmatch(r"\d{1,3}", compact):
        features.add("digits_only_short")
    digit_count = len(re.findall(r"\d", compact))
    if digit_count / max(char_count, 1) >= 0.65:
        features.add("mostly_digits")
    zh_count = len(re.findall(r"[\u4e00-\u9fff]", compact))
    if zh_count:
        features.add("has_chinese")
    if zh_count / max(char_count, 1) >= 0.45:
        features.add("mostly_chinese")
    if len(re.findall(r"[A-H][\.\、．)]", text)) >= 2:
        features.add("dense_options")
    return features


def _bucket(value: int, boundaries: tuple[int, ...]) -> str:
    for boundary in boundaries:
        if value <= boundary:
            return f"<= {boundary}"
    return f"> {boundaries[-1]}"


def _is_high_signal_line(text: str) -> bool:
    return bool(
        _QUESTION_START_PATTERN.match(text)
        or _SECTION_HEADER_PATTERN.match(text)
        or _OPTION_LINE_PATTERN.match(text)
        or len(re.findall(r"[A-H][\.\、．)]", text)) >= 2
        or "答案" in text
        or "解析" in text
    )


def _split_lines(text: str) -> list[str]:
    return [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").splitlines() if line.strip()]


def _normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", str(line or "").strip())


def _normalize_compact(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").strip())


def _is_supported_artifact(artifact: dict[str, Any] | None) -> bool:
    return bool(isinstance(artifact, dict) and artifact.get("artifact_type") == OCR_LINE_FILTER_ARTIFACT_TYPE and isinstance(artifact.get("model"), dict))


def _model_registry_root() -> Path:
    try:
        from app.core.config import get_settings

        return get_settings().storage.root_path / "models" / "ocr_cleaner"
    except Exception:
        root = Path(os.getenv("STORAGE_ROOT") or "data")
        return root / "models" / "ocr_cleaner"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}
