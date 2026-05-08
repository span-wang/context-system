from __future__ import annotations

import asyncio
import json
import re
import threading
import unicodedata
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models import ExamQuestion, KnowledgePoint, QuestionKnowledgeLink
from app.services.tagging import rank_knowledge_candidates
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
_AI_TAG_BATCH_SHARED_POINT_LIMIT = 48
_AI_TAG_BATCH_PER_QUESTION_POINT_LIMIT = 12


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


@dataclass(slots=True)
class AIKnowledgeReviewResult:
    approved_link_ids: list[int]
    rejected_link_ids: list[int]
    primary_link_id: int | None = None
    used_ai: bool = False
    error: str | None = None


@dataclass(slots=True)
class AIQuestionProcessResult:
    changed: bool = False
    created_links: int = 0
    review_status: str | None = None
    review_note: str | None = None
    used_ai: bool = False
    error: str | None = None


def normalize_question_fields(question: ExamQuestion) -> bool:
    changed = False

    stem = normalize_question_text(question.stem_text)
    stem = _strip_leading_question_number(stem, question.question_no)
    if stem and stem != question.stem_text:
        question.stem_text = stem
        changed = True

    options = normalize_options(question.options_json)
    if options != (question.options_json or []):
        question.options_json = options
        changed = True

    answer = normalize_answer(question.answer_text, question.question_type)
    if answer != question.answer_text:
        question.answer_text = answer
        changed = True

    analysis = normalize_analysis(question.analysis_text)
    if analysis != question.analysis_text:
        question.analysis_text = analysis
        changed = True

    if changed and question.parse_status in {"pending", "parsed", "needs_review"}:
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


def question_needs_solution(question: ExamQuestion) -> bool:
    return _is_missing_text(question.answer_text) or _is_missing_text(question.analysis_text)


def complete_missing_solution_with_ai(
    question: ExamQuestion,
    *,
    subject_name: str | None = None,
) -> AIQuestionResult:
    if not question_needs_solution(question):
        return AIQuestionResult()

    provider, endpoint = _get_reviewer_provider()
    if provider is None or endpoint is None:
        return AIQuestionResult(error="reviewer_llm_unavailable")

    try:
        payload = _run_async(
            _request_question_completion(
                provider,
                question=question,
                subject_name=subject_name,
                max_tokens=min(endpoint.max_tokens, 1600),
            )
        )
    except Exception as exc:
        return AIQuestionResult(used_ai=True, error=str(exc)[:200])

    changed = _apply_completion_payload(question, payload)
    if changed:
        question.parse_status = "ai_enriched"
        question.review_status = "needs_revision" if question.review_status == "pending" else question.review_status
        question.review_note = _append_review_note(question.review_note, "AI已补全答案/解析，建议人工复核。")
    return AIQuestionResult(changed=changed, used_ai=True)


def review_question_with_ai(
    question: ExamQuestion,
    *,
    subject_name: str | None = None,
) -> AIQuestionReviewResult:
    provider, endpoint = _get_reviewer_provider()
    if provider is None or endpoint is None:
        return AIQuestionReviewResult(error="reviewer_llm_unavailable")

    try:
        payload = _run_async(
            _request_question_review(
                provider,
                question=question,
                subject_name=subject_name,
                max_tokens=min(endpoint.max_tokens, 1200),
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


def review_knowledge_links_with_ai(
    question: ExamQuestion,
    links: list[QuestionKnowledgeLink],
    point_by_id: dict[int, KnowledgePoint],
) -> AIKnowledgeReviewResult:
    if not links:
        return AIKnowledgeReviewResult(approved_link_ids=[], rejected_link_ids=[], error="no_links")

    provider, endpoint = _get_reviewer_provider()
    if provider is None or endpoint is None:
        return AIKnowledgeReviewResult(approved_link_ids=[], rejected_link_ids=[], error="reviewer_llm_unavailable")

    try:
        payload = _run_async(
            _request_knowledge_review(
                provider,
                question=question,
                links=links,
                point_by_id=point_by_id,
                max_tokens=min(endpoint.max_tokens, 1400),
            )
        )
    except Exception as exc:
        return AIKnowledgeReviewResult(approved_link_ids=[], rejected_link_ids=[], used_ai=True, error=str(exc)[:200])

    valid_ids = {link.id for link in links}
    approved_ids = _normalize_link_id_list(payload.get("approved_link_ids"), valid_ids)
    rejected_ids = [link_id for link_id in _normalize_link_id_list(payload.get("rejected_link_ids"), valid_ids) if link_id not in approved_ids]
    primary_link_id = _normalize_optional_link_id(payload.get("primary_link_id"), valid_ids)
    if approved_ids and primary_link_id not in approved_ids:
        primary_link_id = approved_ids[0]
    if not approved_ids:
        primary_link_id = None
    if not approved_ids and not rejected_ids:
        return AIKnowledgeReviewResult(approved_link_ids=[], rejected_link_ids=[], used_ai=True, error="empty_review_result")
    return AIKnowledgeReviewResult(
        approved_link_ids=approved_ids,
        rejected_link_ids=rejected_ids,
        primary_link_id=primary_link_id,
        used_ai=True,
    )


def apply_ai_tags(
    session: Session,
    question: ExamQuestion,
    points: list[KnowledgePoint],
    tenant_id: int,
    operator_id: int | None = None,
    *,
    limit: int = 3,
) -> list[QuestionKnowledgeLink]:
    if not points:
        return []

    provider, endpoint = _get_reviewer_provider()
    if provider is None or endpoint is None:
        return []

    candidates = _select_ai_mapping_points(points, question, max_points=120)
    if not candidates:
        return []

    try:
        payload = _run_async(
            _request_knowledge_mapping(
                provider,
                question=question,
                points=candidates,
                max_tokens=min(endpoint.max_tokens, 1400),
            )
        )
    except Exception:
        return []

    return _create_ai_links(
        session,
        question=question,
        points=candidates,
        payload=payload,
        tenant_id=tenant_id,
        operator_id=operator_id,
        limit=limit,
    )


def apply_ai_tags_batch(
    session: Session,
    questions: list[ExamQuestion],
    points: list[KnowledgePoint],
    tenant_id: int,
    operator_id: int | None = None,
    *,
    limit: int = 3,
) -> dict[int, list[QuestionKnowledgeLink]]:
    if not questions or not points:
        return {}

    provider, endpoint = _get_reviewer_provider()
    if provider is None or endpoint is None:
        return {}

    candidates = _select_batch_ai_mapping_points(
        points,
        questions,
        max_points=_AI_TAG_BATCH_SHARED_POINT_LIMIT,
        per_question_limit=_AI_TAG_BATCH_PER_QUESTION_POINT_LIMIT,
    )
    if not candidates:
        return {}

    try:
        payload = _run_async(
            _request_batch_knowledge_mapping(
                provider,
                questions=questions,
                points=candidates,
                max_tokens=min(endpoint.max_tokens, 2600),
            )
        )
    except Exception:
        return {}

    return _create_batch_ai_links(
        session,
        questions=questions,
        points=candidates,
        payload=payload,
        tenant_id=tenant_id,
        operator_id=operator_id,
        limit=limit,
    )


def process_question_with_ai(
    session: Session,
    question: ExamQuestion,
    points: list[KnowledgePoint],
    tenant_id: int,
    operator_id: int | None = None,
    *,
    subject_name: str | None = None,
    limit: int = 3,
) -> AIQuestionProcessResult:
    provider, endpoint = _get_reviewer_provider()
    if provider is None or endpoint is None:
        return AIQuestionProcessResult(error="reviewer_llm_unavailable")

    candidates = _select_ai_mapping_points(points, question, max_points=48)
    try:
        payload = _run_async(
            _request_question_process(
                provider,
                question=question,
                points=candidates,
                subject_name=subject_name,
                max_tokens=min(endpoint.max_tokens, 2200),
            )
        )
    except Exception as exc:
        return AIQuestionProcessResult(used_ai=True, error=str(exc)[:200])

    changed = _apply_process_completion_payload(question, payload)
    created_links = len(
        _create_ai_links(
            session,
            question=question,
            points=candidates,
            payload={"mappings": payload.get("mappings")},
            tenant_id=tenant_id,
            operator_id=operator_id,
            limit=limit,
        )
    )

    review_status = str(payload.get("review_status") or "").strip()
    if review_status not in {"approved", "needs_revision", "rejected"}:
        review_status = None
    review_note = normalize_question_text(str(payload.get("review_note") or "")) or None
    if review_status:
        question.review_status = review_status
        question.review_note = review_note
    elif changed and not question.review_note:
        question.review_note = "AI已补全内容，建议人工复核。"
    if changed:
        question.parse_status = "ai_enriched"
    return AIQuestionProcessResult(
        changed=changed,
        created_links=created_links,
        review_status=review_status,
        review_note=review_note,
        used_ai=True,
    )


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


async def _request_question_completion(
    provider: Any,
    *,
    question: ExamQuestion,
    subject_name: str | None,
    max_tokens: int,
) -> dict[str, Any]:
    text = _format_question(question)
    prompt = (
        "请规范化题目并在缺失时补全参考答案和解析。\n"
        "要求：\n"
        "1. 只根据题干、选项和通用考试知识作答，不确定时 answer 或 analysis 留空。\n"
        "2. 客观题答案只返回选项字母；判断题返回“正确”或“错误”。\n"
        "3. 解析要解释关键依据，不要编造具体年份、条文号、税率或教材原文。\n"
        "4. 去掉 OCR 乱码、页眉页脚、水印、网址、公众号等噪音，保留必要公式和题意。\n"
        "5. 只输出 JSON，不要 Markdown 代码块。\n\n"
        f"学科：{subject_name or '未填写'}\n"
        f"题型：{question.question_type}\n"
        f"题目：\n{text}"
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
    try:
        payload = await provider.chat_json(
            [
                {"role": "system", "content": "你是严谨的中文考试题目清洗与解析助手。"},
                {"role": "user", "content": prompt},
            ],
            schema,
            max_tokens=max_tokens,
        )
    except json.JSONDecodeError:
        text_response = await provider.chat(
            [
                {"role": "system", "content": "你是严谨的中文考试题目清洗与解析助手，只返回 JSON。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
        )
        payload = json.loads(_extract_json_object(text_response))
    return payload if isinstance(payload, dict) else {}


async def _request_question_review(
    provider: Any,
    *,
    question: ExamQuestion,
    subject_name: str | None,
    max_tokens: int,
) -> dict[str, Any]:
    prompt = (
        "请审核一道中文考试原始题，判断它是否可以直接进入题库复核通过。\n"
        "审核标准：题干是否完整清晰、题型与结构是否匹配、选项是否规整、答案/解析是否足够支撑使用、是否有明显 OCR 乱码或缺段。\n"
        "输出要求：\n"
        "1. review_status 只能是 approved、needs_revision、rejected 三选一。\n"
        "2. review_note 用简短中文说明主要原因，适合直接展示给人工复核人员。\n"
        "3. 若只是局部缺答案、解析、格式噪音，优先给 needs_revision，不要轻易给 rejected。\n"
        "4. 只输出 JSON，不要 Markdown 代码块。\n\n"
        f"学科：{subject_name or '未填写'}\n"
        f"题型：{question.question_type}\n"
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
    try:
        payload = await provider.chat_json(
            [
                {"role": "system", "content": "你是严谨的中文考试题目审核助手。"},
                {"role": "user", "content": prompt},
            ],
            schema,
            max_tokens=max_tokens,
        )
    except json.JSONDecodeError:
        text_response = await provider.chat(
            [
                {"role": "system", "content": "你是严谨的中文考试题目审核助手，只返回 JSON。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
        )
        payload = json.loads(_extract_json_object(text_response))
    return payload if isinstance(payload, dict) else {}


async def _request_knowledge_mapping(
    provider: Any,
    *,
    question: ExamQuestion,
    points: list[KnowledgePoint],
    max_tokens: int,
) -> dict[str, Any]:
    point_lines = []
    for point in points:
        keywords = "、".join(str(item) for item in (point.keywords_json or [])[:8])
        desc = normalize_question_text(point.description or "")[:80]
        point_lines.append(f"{point.id}. {point.path or point.name} | 关键词：{keywords} | 说明：{desc}")
    prompt = (
        "请把题目映射到最相关的已有考点。只能选择下面列表里的 knowledge_point_id，不要创造新考点。\n"
        "返回 1-3 个候选，最主要考点 is_primary=true。证据必须摘自题干、选项、答案或解析中的短语。\n"
        "只输出 JSON，不要 Markdown 代码块。\n\n"
        f"题目：\n{_format_question(question)}\n\n"
        "可选考点：\n"
        + "\n".join(point_lines)
    )
    schema = {
        "type": "object",
        "properties": {
            "mappings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "knowledge_point_id": {"type": "integer"},
                        "confidence": {"type": "number"},
                        "evidence": {"type": "string"},
                        "is_primary": {"type": "boolean"},
                    },
                    "required": ["knowledge_point_id", "confidence", "evidence"],
                },
            }
        },
        "required": ["mappings"],
    }
    try:
        payload = await provider.chat_json(
            [
                {"role": "system", "content": "你是严谨的中文考试考点标注助手。"},
                {"role": "user", "content": prompt},
            ],
            schema,
            max_tokens=max_tokens,
        )
    except json.JSONDecodeError:
        text_response = await provider.chat(
            [
                {"role": "system", "content": "你是严谨的中文考试考点标注助手，只返回 JSON。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
        )
        payload = json.loads(_extract_json_object(text_response))
    return payload if isinstance(payload, dict) else {}


async def _request_batch_knowledge_mapping(
    provider: Any,
    *,
    questions: list[ExamQuestion],
    points: list[KnowledgePoint],
    max_tokens: int,
) -> dict[str, Any]:
    point_lines = []
    for point in points:
        keywords = "、".join(str(item) for item in (point.keywords_json or [])[:8])
        desc = normalize_question_text(point.description or "")[:80]
        point_lines.append(f"{point.id}. {point.path or point.name} | 关键词：{keywords} | 说明：{desc}")

    question_lines = []
    for question in questions:
        question_lines.append(
            "\n".join(
                [
                    f"question_id={question.id}",
                    f"question_no={question.question_no}",
                    _format_question(question),
                ]
            )
        )

    prompt = (
        "请把下面多道题映射到最相关的已有考点。只能选择下面列表里的 knowledge_point_id，不要创造新考点。\n"
        "对每道题返回 1-3 个候选，最主要考点 is_primary=true。证据必须摘自该题题干、选项、答案或解析中的短语。\n"
        "如果某题没有足够把握，可以返回空 mappings。\n"
        "只输出 JSON，不要 Markdown 代码块。\n\n"
        "题目列表：\n"
        + "\n\n---\n\n".join(question_lines)
        + "\n\n可选考点：\n"
        + "\n".join(point_lines)
    )
    schema = {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question_id": {"type": "integer"},
                        "mappings": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "knowledge_point_id": {"type": "integer"},
                                    "confidence": {"type": "number"},
                                    "evidence": {"type": "string"},
                                    "is_primary": {"type": "boolean"},
                                },
                                "required": ["knowledge_point_id", "confidence", "evidence"],
                            },
                        },
                    },
                    "required": ["question_id", "mappings"],
                },
            }
        },
        "required": ["results"],
    }
    try:
        payload = await provider.chat_json(
            [
                {"role": "system", "content": "你是严谨的中文考试考点标注助手。"},
                {"role": "user", "content": prompt},
            ],
            schema,
            max_tokens=max_tokens,
        )
    except json.JSONDecodeError:
        text_response = await provider.chat(
            [
                {"role": "system", "content": "你是严谨的中文考试考点标注助手，只返回 JSON。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
        )
        payload = json.loads(_extract_json_object(text_response))
    return payload if isinstance(payload, dict) else {}


async def _request_question_process(
    provider: Any,
    *,
    question: ExamQuestion,
    points: list[KnowledgePoint],
    subject_name: str | None,
    max_tokens: int,
) -> dict[str, Any]:
    point_lines = []
    for point in points:
        keywords = "、".join(str(item) for item in (point.keywords_json or [])[:8])
        desc = normalize_question_text(point.description or "")[:80]
        point_lines.append(f"{point.id}. {point.path or point.name} | 关键词：{keywords} | 说明：{desc}")

    prompt = (
        "请对这道中文考试题一次性完成：题目清洗补全、考点映射、可用性复核。\n"
        "要求：\n"
        "1. 先规范化题干和选项；缺失时补全答案和解析，不确定时留空。\n"
        "2. 只从给定候选考点中选择 1-3 个最相关的 knowledge_point_id，不要创造新考点。\n"
        "3. review_status 只能是 approved、needs_revision、rejected 三选一。\n"
        "4. review_note 用简短中文说明主要原因，可直接展示给人工复核人员。\n"
        "5. 客观题答案只返回选项字母；判断题返回“正确”或“错误”。\n"
        "6. 证据必须摘自题干、选项、答案或解析中的短语。\n"
        "7. 只输出 JSON，不要 Markdown 代码块。\n\n"
        f"学科：{subject_name or '未填写'}\n"
        f"题型：{question.question_type}\n"
        f"题目：\n{_format_question(question)}\n\n"
        "可选考点：\n"
        + "\n".join(point_lines)
    )
    schema = {
        "type": "object",
        "properties": {
            "normalized_stem": {"type": "string"},
            "normalized_options": {"type": "array", "items": {"type": "string"}},
            "answer": {"type": "string"},
            "analysis": {"type": "string"},
            "mappings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "knowledge_point_id": {"type": "integer"},
                        "confidence": {"type": "number"},
                        "evidence": {"type": "string"},
                        "is_primary": {"type": "boolean"},
                    },
                    "required": ["knowledge_point_id", "confidence", "evidence"],
                },
            },
            "review_status": {"type": "string"},
            "review_note": {"type": "string"},
        },
        "required": [
            "normalized_stem",
            "normalized_options",
            "answer",
            "analysis",
            "mappings",
            "review_status",
            "review_note",
        ],
    }
    try:
        payload = await provider.chat_json(
            [
                {"role": "system", "content": "你是严谨的中文考试题目清洗、考点标注与复核助手。"},
                {"role": "user", "content": prompt},
            ],
            schema,
            max_tokens=max_tokens,
        )
    except json.JSONDecodeError:
        text_response = await provider.chat(
            [
                {"role": "system", "content": "你是严谨的中文考试题目清洗、考点标注与复核助手，只返回 JSON。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
        )
        payload = json.loads(_extract_json_object(text_response))
    return payload if isinstance(payload, dict) else {}


async def _request_knowledge_review(
    provider: Any,
    *,
    question: ExamQuestion,
    links: list[QuestionKnowledgeLink],
    point_by_id: dict[int, KnowledgePoint],
    max_tokens: int,
) -> dict[str, Any]:
    link_lines = []
    for link in links:
        point = point_by_id.get(link.knowledge_point_id)
        point_label = point.path if point and point.path else point.name if point else f"考点#{link.knowledge_point_id}"
        link_lines.append(
            f"link_id={link.id} | 考点={point_label} | 证据={normalize_question_text(link.evidence_text or '')[:120] or '无'} | "
            f"来源={link.tag_source or '-'} | 置信度={link.confidence_score if link.confidence_score is not None else '-'}"
        )
    prompt = (
        "请审核下面这道题的候选考点。\n"
        "要求：\n"
        "1. 只能在给定的 link_id 中做选择，不要创建新考点。\n"
        "2. 把合适的候选放到 approved_link_ids，不合适的放到 rejected_link_ids。\n"
        "3. 如果有通过候选，必须指定一个 primary_link_id，且 primary_link_id 必须属于 approved_link_ids。\n"
        "4. 证据只能依据题干、选项、答案、解析，不要脑补教材原文。\n"
        "5. 只输出 JSON，不要 Markdown 代码块。\n\n"
        f"题目：\n{_format_question(question)}\n\n"
        "候选考点：\n"
        + "\n".join(link_lines)
    )
    schema = {
        "type": "object",
        "properties": {
            "approved_link_ids": {"type": "array", "items": {"type": "integer"}},
            "rejected_link_ids": {"type": "array", "items": {"type": "integer"}},
            "primary_link_id": {"type": ["integer", "null"]},
        },
        "required": ["approved_link_ids", "rejected_link_ids", "primary_link_id"],
    }
    try:
        payload = await provider.chat_json(
            [
                {"role": "system", "content": "你是严谨的中文考试考点审核助手。"},
                {"role": "user", "content": prompt},
            ],
            schema,
            max_tokens=max_tokens,
        )
    except json.JSONDecodeError:
        text_response = await provider.chat(
            [
                {"role": "system", "content": "你是严谨的中文考试考点审核助手，只返回 JSON。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
        )
        payload = json.loads(_extract_json_object(text_response))
    return payload if isinstance(payload, dict) else {}


def _apply_completion_payload(question: ExamQuestion, payload: dict[str, Any]) -> bool:
    changed = False
    stem = normalize_question_text(str(payload.get("normalized_stem") or ""))
    if stem and len(stem) >= 6 and stem != question.stem_text:
        question.stem_text = _strip_leading_question_number(stem, question.question_no)
        changed = True

    raw_options = payload.get("normalized_options")
    if isinstance(raw_options, list):
        options = normalize_options([str(item) for item in raw_options])
        if options and options != (question.options_json or []):
            question.options_json = options
            changed = True

    if _is_missing_text(question.answer_text):
        answer = normalize_answer(str(payload.get("answer") or ""), question.question_type)
        if answer:
            question.answer_text = answer
            changed = True

    if _is_missing_text(question.analysis_text):
        analysis = normalize_analysis(str(payload.get("analysis") or ""))
        if analysis:
            question.analysis_text = analysis
            changed = True
    return changed


def _apply_process_completion_payload(question: ExamQuestion, payload: dict[str, Any]) -> bool:
    changed = False
    stem = normalize_question_text(str(payload.get("normalized_stem") or ""))
    if stem and len(stem) >= 6 and stem != question.stem_text:
        question.stem_text = _strip_leading_question_number(stem, question.question_no)
        changed = True

    raw_options = payload.get("normalized_options")
    if isinstance(raw_options, list):
        options = normalize_options([str(item) for item in raw_options])
        if options and options != (question.options_json or []):
            question.options_json = options
            changed = True

    answer = normalize_answer(str(payload.get("answer") or ""), question.question_type)
    if answer and answer != question.answer_text:
        question.answer_text = answer
        changed = True

    analysis = normalize_analysis(str(payload.get("analysis") or ""))
    if analysis and analysis != question.analysis_text:
        question.analysis_text = analysis
        changed = True
    return changed


def _create_ai_links(
    session: Session,
    *,
    question: ExamQuestion,
    points: list[KnowledgePoint],
    payload: dict[str, Any],
    tenant_id: int,
    operator_id: int | None,
    limit: int,
) -> list[QuestionKnowledgeLink]:
    point_by_id = {point.id: point for point in points}
    existing_rows = (
        session.query(QuestionKnowledgeLink.knowledge_point_id, QuestionKnowledgeLink.is_primary)
        .filter(QuestionKnowledgeLink.question_id == question.id)
        .all()
    )
    existing_point_ids = {row[0] for row in existing_rows}
    has_primary = any(bool(row[1]) for row in existing_rows)
    raw_mappings = payload.get("mappings") if isinstance(payload, dict) else []
    if not isinstance(raw_mappings, list):
        return []

    created: list[QuestionKnowledgeLink] = []
    for item in raw_mappings:
        if not isinstance(item, dict):
            continue
        try:
            point_id = int(item.get("knowledge_point_id"))
        except (TypeError, ValueError):
            continue
        point = point_by_id.get(point_id)
        if point is None or point_id in existing_point_ids:
            continue
        confidence = _clamp_confidence(item.get("confidence"))
        if confidence < 0.45:
            continue
        evidence = normalize_question_text(str(item.get("evidence") or ""))[:120]
        is_primary = bool(item.get("is_primary")) and not has_primary and not created
        if not has_primary and not created:
            is_primary = True
        link = QuestionKnowledgeLink(
            tenant_id=tenant_id,
            question_id=question.id,
            question_layer="raw",
            knowledge_point_id=point.id,
            link_type="ai_candidate",
            confidence_score=confidence,
            evidence_text=evidence or question.stem_text[:80],
            tag_source="ai_reviewer",
            is_primary=is_primary,
            review_status="pending",
            created_by=operator_id,
            updated_by=operator_id,
        )
        session.add(link)
        created.append(link)
        existing_point_ids.add(point_id)
        if is_primary:
            has_primary = True
        if len(created) >= limit:
            break
    if created:
        session.flush()
    return created


def _create_batch_ai_links(
    session: Session,
    *,
    questions: list[ExamQuestion],
    points: list[KnowledgePoint],
    payload: dict[str, Any],
    tenant_id: int,
    operator_id: int | None,
    limit: int,
) -> dict[int, list[QuestionKnowledgeLink]]:
    question_by_id = {question.id: question for question in questions}
    raw_results = payload.get("results") if isinstance(payload, dict) else []
    if not isinstance(raw_results, list):
        return {}

    created_by_question: dict[int, list[QuestionKnowledgeLink]] = {}
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        try:
            question_id = int(item.get("question_id"))
        except (TypeError, ValueError):
            continue
        question = question_by_id.get(question_id)
        if question is None:
            continue
        created = _create_ai_links(
            session,
            question=question,
            points=points,
            payload={"mappings": item.get("mappings")},
            tenant_id=tenant_id,
            operator_id=operator_id,
            limit=limit,
        )
        if created:
            created_by_question[question_id] = created
    return created_by_question


def _select_ai_mapping_points(
    points: list[KnowledgePoint],
    question: ExamQuestion,
    *,
    max_points: int,
) -> list[KnowledgePoint]:
    text = _format_question(question)
    ranked = [candidate.point for candidate in rank_knowledge_candidates(points, text, limit=max_points)]
    selected: list[KnowledgePoint] = []
    seen: set[int] = set()
    for point in ranked + points:
        if point.id in seen:
            continue
        selected.append(point)
        seen.add(point.id)
        if len(selected) >= max_points:
            break
    return selected


def _select_batch_ai_mapping_points(
    points: list[KnowledgePoint],
    questions: list[ExamQuestion],
    *,
    max_points: int,
    per_question_limit: int,
) -> list[KnowledgePoint]:
    selected: list[KnowledgePoint] = []
    seen: set[int] = set()

    for question in questions:
        text = _format_question(question)
        ranked = rank_knowledge_candidates(points, text, limit=per_question_limit)
        for candidate in ranked:
            point = candidate.point
            if point.id in seen:
                continue
            selected.append(point)
            seen.add(point.id)
            if len(selected) >= max_points:
                return selected

    for point in points:
        if point.id in seen:
            continue
        selected.append(point)
        seen.add(point.id)
        if len(selected) >= max_points:
            break
    return selected


def _format_question(question: ExamQuestion) -> str:
    parts = [
        f"题干：{question.stem_text}",
        "选项：" + ("\n".join(question.options_json or []) if question.options_json else "无"),
        f"答案：{question.answer_text or '缺失'}",
        f"解析：{question.analysis_text or '缺失'}",
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


def _append_review_note(existing: str | None, note: str) -> str:
    if not existing:
        return note
    if note in existing:
        return existing
    return f"{existing}；{note}"


def _normalize_link_id_list(value: Any, valid_ids: set[int]) -> list[int]:
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for item in value:
        try:
            link_id = int(item)
        except (TypeError, ValueError):
            continue
        if link_id not in valid_ids or link_id in result:
            continue
        result.append(link_id)
    return result


def _normalize_optional_link_id(value: Any, valid_ids: set[int]) -> int | None:
    try:
        link_id = int(value)
    except (TypeError, ValueError):
        return None
    return link_id if link_id in valid_ids else None


def _clamp_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.68
    if confidence > 1:
        confidence = confidence / 100
    return round(max(0.0, min(0.98, confidence)), 2)
