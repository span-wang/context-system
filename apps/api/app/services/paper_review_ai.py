from __future__ import annotations

import asyncio
import json
import re
import threading
import unicodedata
from dataclasses import dataclass
from typing import Any

from llm.providers import get_llm_provider
from settings import get_settings as get_llm_settings
from settings import resolve_llm_api_key


_REMOTE_LLM_PROVIDERS = {"openai_compat", "deepseek", "anthropic"}
_ZERO_WIDTH_PATTERN = re.compile(r"[\u200b-\u200f\u202a-\u202e\ufeff]")
_CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_REPEATED_BLANK_PATTERN = re.compile(r"\n{3,}")
_MISSING_VALUES = {
    "",
    "-",
    "--",
    "—",
    "无",
    "暂无",
    "无答案",
    "暂无答案",
    "无解析",
    "暂无解析",
    "未识别",
    "未提供",
    "答案缺失",
    "解析缺失",
    "none",
    "null",
}
_ANSWER_PREFIX_PATTERN = re.compile(r"^(?:参考答案|正确答案|答案|answer)\s*[:：]?\s*", re.IGNORECASE)
_ANALYSIS_PREFIX_PATTERN = re.compile(r"^(?:答案解析|解析|analysis)\s*[:：]?\s*", re.IGNORECASE)
_OPTION_LABEL_PATTERN = re.compile(r"^\s*([A-Ha-h])\s*[\.\、．\)]?\s*(.+)$", re.S)
_OBJECTIVE_TYPES = {"single_choice", "multiple_choice", "judge"}


@dataclass(slots=True)
class AIQuestionResult:
    changed: bool = False
    used_ai: bool = False
    error: str | None = None


@dataclass(slots=True)
class AIQuestionReviewResult:
    review_status: str | None = None
    review_note: str | None = None
    used_ai: bool = False
    error: str | None = None


def normalize_question_fields(question: Any) -> bool:
    changed = False

    stem = normalize_question_text(question.stem_text)
    stem = _strip_leading_question_number(stem, getattr(question, "question_no", None))
    if stem and stem != question.stem_text:
        question.stem_text = stem
        changed = True

    options = normalize_options(getattr(question, "options_json", None))
    if options != (getattr(question, "options_json", None) or []):
        question.options_json = options
        changed = True

    answer = normalize_answer(getattr(question, "answer_text", None), getattr(question, "question_type", None))
    if answer != getattr(question, "answer_text", None):
        question.answer_text = answer
        changed = True

    analysis = normalize_analysis(getattr(question, "analysis_text", None))
    if analysis != getattr(question, "analysis_text", None):
        question.analysis_text = analysis
        changed = True

    if changed and getattr(question, "parse_status", None) in {"pending", "parsed", "needs_review", "manual_updated"}:
        question.parse_status = "normalized"
    return changed


def normalize_question_text(value: str | None) -> str:
    return _clean_text(value, strip_noise_lines=True)


def normalize_options(options: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for option in options or []:
        text = _clean_text(str(option), strip_noise_lines=True).replace("\n", " ")
        match = _OPTION_LABEL_PATTERN.match(text)
        if match:
            text = f"{match.group(1).upper()}. {match.group(2).strip()}"
        text = re.sub(r"\s+", " ", text).strip()
        if not text or _is_missing_text(text) or _looks_like_noise_line(text):
            continue
        key = text.lower()
        if key in seen:
            continue
        normalized.append(text)
        seen.add(key)
    return normalized


def normalize_answer(value: str | None, question_type: str | None = None) -> str | None:
    text = _clean_text(value, strip_noise_lines=True)
    if not text:
        return None
    text = _ANSWER_PREFIX_PATTERN.sub("", text).strip()
    text = re.sub(r"\s+", " ", text).strip()
    if _is_missing_text(text):
        return None
    if question_type in _OBJECTIVE_TYPES:
        upper = text.upper()
        if question_type in {"single_choice", "multiple_choice"}:
            letters = re.findall(r"[A-H]", upper)
            if letters:
                return "".join(dict.fromkeys(letters))
        if question_type == "judge":
            if re.search(r"(不正确|错误|错|FALSE|×|X)", upper):
                return "错误"
            if re.search(r"(正确|对|TRUE|√)", upper):
                return "正确"
    return text


def normalize_analysis(value: str | None) -> str | None:
    text = _clean_text(value, strip_noise_lines=True)
    if not text:
        return None
    text = _ANALYSIS_PREFIX_PATTERN.sub("", text).strip()
    if _is_missing_text(text):
        return None
    return text


def standardize_question_with_ai(question: Any, *, subject_name: str | None = None) -> AIQuestionResult:
    provider, endpoint = _get_reviewer_provider()
    if provider is None or endpoint is None:
        return AIQuestionResult(error="reviewer_llm_unavailable")

    try:
        payload = _run_async(
            _request_question_standardization(
                provider,
                question=question,
                subject_name=subject_name,
                max_tokens=min(endpoint.max_tokens, 1800),
            )
        )
    except Exception as exc:
        return AIQuestionResult(used_ai=True, error=str(exc)[:200])

    changed = _apply_standardization_payload(question, payload)
    if changed:
        question.parse_status = "ai_enriched"
    return AIQuestionResult(changed=changed, used_ai=True)


def review_question_with_ai(question: Any, *, subject_name: str | None = None) -> AIQuestionReviewResult:
    provider, endpoint = _get_reviewer_provider()
    if provider is None or endpoint is None:
        return AIQuestionReviewResult(error="reviewer_llm_unavailable")

    try:
        payload = _run_async(
            _request_question_review(
                provider,
                question=question,
                subject_name=subject_name,
                max_tokens=min(endpoint.max_tokens, 1300),
            )
        )
    except Exception as exc:
        return AIQuestionReviewResult(used_ai=True, error=str(exc)[:200])

    review_status = str(payload.get("review_status") or "").strip()
    review_note = normalize_question_text(str(payload.get("review_note") or "")) or None
    if review_status not in {"approved", "needs_revision", "rejected"}:
        return AIQuestionReviewResult(used_ai=True, error="invalid_review_status")
    return AIQuestionReviewResult(
        review_status=review_status,
        review_note=review_note,
        used_ai=True,
    )


async def _request_question_standardization(
    provider: Any,
    *,
    question: Any,
    subject_name: str | None,
    max_tokens: int,
) -> dict[str, Any]:
    prompt = (
        "请对这道中文考试题做题目补全与标准化。\n"
        "要求：\n"
        "1. 清除 OCR 噪音、页眉页脚、水印、网址、公众号、乱码和重复残片。\n"
        "2. 规范题干、选项、答案、解析的表达，保留原意，不要擅自改题。\n"
        "3. 若答案或解析缺失，可根据题干和选项尽量补全；不确定时保持为空。\n"
        "4. 客观题答案只返回选项字母；判断题返回“正确”或“错误”。\n"
        "5. 只输出 JSON，不要 Markdown 代码块。\n\n"
        f"学科：{subject_name or '未填写'}\n"
        f"题型：{getattr(question, 'question_type', '')}\n"
        f"题目：\n{_format_question(question)}"
    )
    schema = {
        "type": "object",
        "properties": {
            "normalized_stem": {"type": "string"},
            "normalized_options": {"type": "array", "items": {"type": "string"}},
            "answer": {"type": "string"},
            "analysis": {"type": "string"},
        },
        "required": ["normalized_stem", "normalized_options", "answer", "analysis"],
    }
    return await _chat_json(
        provider,
        system_prompt="你是严谨的中文考试题目清洗与补全助手。",
        user_prompt=prompt,
        schema=schema,
        max_tokens=max_tokens,
    )


async def _request_question_review(
    provider: Any,
    *,
    question: Any,
    subject_name: str | None,
    max_tokens: int,
) -> dict[str, Any]:
    prompt = (
        "请审核这道中文考试题的答案与解析是否正确、是否彼此一致、是否足以支撑入库。\n"
        "审核标准：\n"
        "1. 答案是否明显错误、缺失、与题型不匹配，或与解析结论冲突。\n"
        "2. 解析是否解释了为何该答案成立，是否存在明显事实性错误或方向性错误。\n"
        "3. 如果无法完全确认正确性，但发现缺漏、歧义、依据不足，给 needs_revision。\n"
        "4. review_status 只能是 approved、needs_revision、rejected 三选一。\n"
        "5. review_note 用简短中文说明主要问题，适合直接给人工审核员看。\n"
        "6. 只输出 JSON，不要 Markdown 代码块。\n\n"
        f"学科：{subject_name or '未填写'}\n"
        f"题型：{getattr(question, 'question_type', '')}\n"
        f"题目：\n{_format_question(question)}"
    )
    schema = {
        "type": "object",
        "properties": {
            "review_status": {"type": "string"},
            "review_note": {"type": "string"},
        },
        "required": ["review_status", "review_note"],
    }
    return await _chat_json(
        provider,
        system_prompt="你是严谨的中文考试答案与解析审核助手。",
        user_prompt=prompt,
        schema=schema,
        max_tokens=max_tokens,
    )


async def _chat_json(
    provider: Any,
    *,
    system_prompt: str,
    user_prompt: str,
    schema: dict[str, Any],
    max_tokens: int,
) -> dict[str, Any]:
    try:
        payload = await provider.chat_json(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            schema,
            max_tokens=max_tokens,
        )
    except json.JSONDecodeError:
        text_response = await provider.chat(
            [
                {"role": "system", "content": f"{system_prompt} 只返回 JSON。"},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
        )
        payload = json.loads(_extract_json_object(text_response))
    return payload if isinstance(payload, dict) else {}


def _apply_standardization_payload(question: Any, payload: dict[str, Any]) -> bool:
    changed = False
    stem = normalize_question_text(str(payload.get("normalized_stem") or ""))
    if stem:
        stem = _strip_leading_question_number(stem, getattr(question, "question_no", None))
        if stem != getattr(question, "stem_text", None):
            question.stem_text = stem
            changed = True

    raw_options = payload.get("normalized_options")
    if isinstance(raw_options, list):
        options = normalize_options([str(item) for item in raw_options])
        if options and options != (getattr(question, "options_json", None) or []):
            question.options_json = options
            changed = True

    answer = normalize_answer(str(payload.get("answer") or ""), getattr(question, "question_type", None))
    if answer and answer != getattr(question, "answer_text", None):
        question.answer_text = answer
        changed = True

    analysis = normalize_analysis(str(payload.get("analysis") or ""))
    if analysis and analysis != getattr(question, "analysis_text", None):
        question.analysis_text = analysis
        changed = True
    return changed


def _clean_text(value: str | None, *, strip_noise_lines: bool) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    text = _ZERO_WIDTH_PATTERN.sub("", text)
    text = _CONTROL_PATTERN.sub("", text)
    text = text.replace("�", "")
    lines: list[str] = []
    blank = False
    for raw_line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if _looks_like_blank_placeholder(line):
            lines.append("（ ）")
            blank = False
            continue
        if strip_noise_lines and _looks_like_noise_line(line):
            continue
        if not line:
            if lines and not blank:
                lines.append("")
                blank = True
            continue
        lines.append(line)
        blank = False
    cleaned = "\n".join(lines).strip()
    cleaned = _REPEATED_BLANK_PATTERN.sub("\n\n", cleaned)
    return cleaned


def _looks_like_noise_line(line: str) -> bool:
    if not line:
        return False
    compact = re.sub(r"\s+", "", line)
    if re.fullmatch(r"(?:第)?\d{1,4}(?:页)?[/／共]\d{1,4}(?:页)?", compact):
        return True
    if re.fullmatch(r"(?:第)?\d{1,4}页", compact, flags=re.IGNORECASE):
        return True
    if re.fullmatch(r"page\d{1,4}(?:of\d{1,4})?", compact, flags=re.IGNORECASE):
        return True
    if re.fullmatch(r"[\W_]{5,}", compact) and not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", compact):
        if re.search(r"[_＿\-—–]+", compact):
            return False
        return True
    watermark_patterns = (
        r"扫描全能王",
        r"camscanner",
        r"公众号",
        r"微信号",
        r"QQ群",
        r"https?://",
        r"www\.",
        r"版权所有",
        r"仅供学习",
        r"禁止转载",
    )
    return len(line) <= 90 and any(re.search(pattern, line, re.IGNORECASE) for pattern in watermark_patterns)


def _looks_like_blank_placeholder(line: str) -> bool:
    if not line:
        return False
    compact = re.sub(r"\s+", "", line)
    return bool(
        re.fullmatch(r"[（(]?[＿_—–-]{2,}[）)]?", compact)
        or re.fullmatch(r"[（(][）)]", compact)
    )


def _strip_leading_question_number(stem: str, question_no: str | None) -> str:
    if not stem:
        return stem
    if question_no:
        pattern = rf"^\s*(?:第\s*)?{re.escape(str(question_no).strip())}\s*[\.\、．\)]\s*"
        stem = re.sub(pattern, "", stem)
    return re.sub(r"^\s*(?:第\s*)?\d{1,3}\s*[\.\、．\)]\s*", "", stem).strip()


def _is_missing_text(value: str | None) -> bool:
    if value is None:
        return True
    text = re.sub(r"\s+", "", str(value)).strip().lower()
    return text in _MISSING_VALUES


def _format_question(question: Any) -> str:
    parts = [
        f"题干：{getattr(question, 'stem_text', '')}",
        "选项：" + ("\n".join(getattr(question, "options_json", None) or []) if getattr(question, "options_json", None) else "无"),
        f"答案：{getattr(question, 'answer_text', None) or '缺失'}",
        f"解析：{getattr(question, 'analysis_text', None) or '缺失'}",
    ]
    return "\n".join(parts)[:12000]


def _get_reviewer_provider() -> tuple[Any | None, Any | None]:
    try:
        settings = get_llm_settings()
        endpoint = settings.llm.reviewer
        provider_name = endpoint.provider.strip()
        if provider_name not in _REMOTE_LLM_PROVIDERS:
            return None, endpoint
        if not resolve_llm_api_key(endpoint, "reviewer"):
            return None, endpoint
        return get_llm_provider(endpoint, target="reviewer"), endpoint
    except Exception:
        return None, None


def _run_async(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except Exception as exc:
            result["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


def _extract_json_object(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        return cleaned[start : end + 1]
    return cleaned
