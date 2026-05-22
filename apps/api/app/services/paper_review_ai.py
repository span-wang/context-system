from __future__ import annotations

import asyncio
import json
import re
import threading
import unicodedata
from dataclasses import dataclass
from typing import Any

from llm.providers import get_llm_provider
from settings import LLMEndpointConfig
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
_OPTION_LABEL_PATTERN = re.compile(r"^\s*([A-Ha-h])(?:[\.\、．\)]\s*|\s+(?=[^A-Za-z]))(.+)$", re.S)
_OBJECTIVE_TYPES = {"single_choice", "multiple_choice", "judge"}
_JUDGE_OPTIONS = ("正确", "错误")


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

    options = normalize_options(getattr(question, "options_json", None), getattr(question, "question_type", None))
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


def normalize_options(options: list[str] | None, question_type: str | None = None) -> list[str]:
    if _is_judge_question_type(question_type):
        return list(_JUDGE_OPTIONS)
    normalized: list[str] = []
    seen: set[str] = set()
    for option in options or []:
        text = _clean_text(str(option), strip_noise_lines=True).replace("\n", " ")
        match = _OPTION_LABEL_PATTERN.match(text)
        if match:
            text = match.group(2).strip()
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


def normalize_analysis(value: Any) -> str | None:
    text = _normalize_analysis_content(value)
    if not text:
        return None
    text = _ANALYSIS_PREFIX_PATTERN.sub("", text).strip()
    if _is_missing_text(text):
        return None
    return text


def _normalize_analysis_content(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        parts: list[str] = []
        for raw_label, raw_body in value.items():
            label = _clean_text(str(raw_label), strip_noise_lines=True).replace("\n", " ").strip("：: ")
            body = _normalize_analysis_content(raw_body)
            if not body:
                continue
            if label:
                parts.append(f"{label}：\n{body}" if "\n" in body else f"{label}：{body}")
            else:
                parts.append(body)
        return "\n\n".join(part for part in parts if part).strip()
    if isinstance(value, (list, tuple)):
        rows: list[str] = []
        for index, item in enumerate(value, start=1):
            body = _normalize_analysis_content(item)
            if not body:
                continue
            body_lines = body.splitlines() or [body]
            rows.append(f"{index}. {body_lines[0]}")
            rows.extend(f"   {line}" for line in body_lines[1:] if line.strip())
        return "\n".join(rows).strip()
    return _clean_text(str(value), strip_noise_lines=True)


def standardize_question_with_ai(
    question: Any,
    *,
    subject_name: str | None = None,
    category_name: str | None = None,
) -> AIQuestionResult:
    provider, endpoint = _get_local_standardizer_provider()
    if provider is None or endpoint is None:
        return AIQuestionResult(error="question_ai_standardizer_unavailable")

    try:
        payload = _run_async(
            _request_question_standardization(
                provider,
                question=question,
                subject_name=subject_name,
                category_name=category_name,
                max_tokens=min(endpoint.max_tokens, 4800),
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
    category_name: str | None,
    max_tokens: int,
) -> dict[str, Any]:
    prompt = (
        "请对这道中文考试题做题目补全与标准化。\n"
        "要求：\n"
        "1. 清除 OCR 噪音、页眉页脚、水印、网址、公众号、乱码和重复残片。\n"
        "2. 规范题干、选项、答案、解析的表达，保留原意，不要擅自改题。\n"
        "3. 若答案或解析缺失，必须先根据题干、选项、共用材料完成解题，再补全答案和解析；除非题干、选项或材料本身严重缺失到无法作答，否则不允许留空。\n"
        "4. 补全出的答案与解析必须彼此一致；解析需要先说明正确答案为何成立，不能只重复答案结论。\n"
        "5. 若题目有选项，解析必须逐项覆盖每个选项，明确写出每个选项为什么对或为什么错；错误选项要点明错在概念、条件、公式、法条、因果或适用范围的哪一点，不能只写“不符合题意”。\n"
        "6. 答案与解析的依据只允许来自当前学科类目的教材或教辅中的通行结论、定义、公式、法条、例题方法；不要引入教材体系外的经验常识、网络资料、超纲延伸或主观猜测。\n"
        "7. `analysis` 必须结构化组织，并根据题目实际情况选择适用模块，不适用的不要硬写：优先列出“考察知识点（考察的是什么）”；计算题要拆成步骤，把常识转成动作流，引导此类题如何下手；遇到易混概念要做辨析；能抽出通用做法时再给套路，但不能脱离本题空泛套模板。\n"
        "8. 客观题答案只返回选项字母；判断题返回“正确”或“错误”。\n"
        "9. 如果题目带有共用材料或题组导语，要结合它们理解子问，但不要把整段材料重复写进答案或解析。\n"
        "10. 只输出 JSON，不要 Markdown 代码块。\n\n"
        f"学科：{subject_name or '未填写'}\n"
        f"类目：{category_name or '未填写'}\n"
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
        system_prompt=(
            "你是严谨的中文考试题目清洗、解题与补全助手。"
            "若原题缺失答案或解析，你必须基于题干、选项、共用材料先完成作答，"
            "再输出可直接入库的答案与解析。"
            "你的答案与解析只能依据当前学科类目的教材或教辅中的通行内容，"
            "不得引用教材体系外的经验、网文说法或主观臆断。"
            "解析要结构化表达，并按题目实际情况选择知识点、步骤、辨析、套路等模块。"
        ),
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
        "6. 如果题目来自材料题/阅读题，要结合共用材料理解子问，不要忽略材料上下文。\n"
        "7. 只输出 JSON，不要 Markdown 代码块。\n\n"
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
        options = normalize_options([str(item) for item in raw_options], getattr(question, "question_type", None))
        if options and options != (getattr(question, "options_json", None) or []):
            question.options_json = options
            changed = True

    answer = normalize_answer(str(payload.get("answer") or ""), getattr(question, "question_type", None))
    if answer and answer != getattr(question, "answer_text", None):
        question.answer_text = answer
        changed = True

    analysis = normalize_analysis(payload.get("analysis"))
    if analysis and analysis != getattr(question, "analysis_text", None):
        question.analysis_text = analysis
        changed = True
    return changed


def _is_judge_question_type(question_type: str | None) -> bool:
    normalized = str(question_type or "").strip()
    return normalized.lower() == "judge" or normalized == "判断题"


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
    parts = [f"节点角色：{getattr(question, 'node_role', '') or 'standalone'}"]
    if getattr(question, "group_stem", None):
        parts.append(f"题组导语：{getattr(question, 'group_stem', '')}")
    if getattr(question, "material_text", None):
        parts.append(f"共用材料：\n{getattr(question, 'material_text', '')}")
    parts.extend(
        [
            f"题干：{getattr(question, 'stem_text', '')}",
            "选项：" + _format_options_for_prompt(getattr(question, "options_json", None)),
            f"答案：{getattr(question, 'answer_text', None) or '缺失'}",
            f"解析：{getattr(question, 'analysis_text', None) or '缺失'}",
        ]
    )
    subquestions = getattr(question, "subquestions", None) or []
    if subquestions:
        parts.append("子问：")
        for index, child in enumerate(subquestions, start=1):
            parts.append(f"{index}. {_format_question(child)}")
    return "\n".join(parts)[:12000]


def _format_options_for_prompt(options: list[str] | None) -> str:
    normalized = normalize_options(options)
    if not normalized:
        return "无"
    return "\n".join(f"{chr(65 + index)}. {option}" for index, option in enumerate(normalized))


def _get_reviewer_provider() -> tuple[Any | None, Any | None]:
    try:
        settings = get_llm_settings()
        endpoint = settings.llm.reviewer
        provider_name = endpoint.provider.strip()
        if provider_name not in _REMOTE_LLM_PROVIDERS:
            return None, endpoint
        if not _allows_missing_api_key(endpoint) and not resolve_llm_api_key(endpoint, "reviewer"):
            return None, endpoint
        return get_llm_provider(endpoint, target="reviewer"), endpoint
    except Exception:
        return None, None


def _get_local_standardizer_provider() -> tuple[Any | None, LLMEndpointConfig | None]:
    try:
        endpoint = get_llm_settings().question_ai_standardizer
        if not getattr(endpoint, "enabled", True):
            return None, endpoint
        provider_name = endpoint.provider.strip()
        if provider_name not in _REMOTE_LLM_PROVIDERS:
            return None, endpoint
        if not _allows_missing_api_key(endpoint) and not resolve_llm_api_key(endpoint, "reviewer"):
            return None, endpoint
        return get_llm_provider(endpoint, target="reviewer"), endpoint
    except Exception:
        return None, None


def _allows_missing_api_key(endpoint: LLMEndpointConfig) -> bool:
    if endpoint.provider.strip() != "openai_compat":
        return False
    normalized = (endpoint.base_url or "").strip().lower()
    return any(
        marker in normalized
        for marker in (
            "127.0.0.1:11434",
            "localhost:11434",
            "0.0.0.0:11434",
            "::1:11434",
        )
    )


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
