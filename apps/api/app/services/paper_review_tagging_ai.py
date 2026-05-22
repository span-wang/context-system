from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass
from typing import Any

from llm.providers import get_llm_provider
from settings import LLMEndpointConfig
from settings import get_settings as get_llm_settings
from settings import resolve_llm_api_key


_REMOTE_LLM_PROVIDERS = {"openai_compat", "deepseek", "anthropic"}


@dataclass(slots=True)
class QuestionTaggingAIResult:
    question_id: int
    point_ids: list[int]
    confidence: float | None = None
    reason: str | None = None
    error: str | None = None


async def auto_tag_questions_with_ollama(
    *,
    questions: list[dict[str, Any]],
    knowledge_points: list[dict[str, Any]],
    concurrency: int = 5,
) -> list[QuestionTaggingAIResult]:
    provider, endpoint = _get_auto_tagger_provider()
    if provider is None or endpoint is None:
        return [
            QuestionTaggingAIResult(
                question_id=int(question["id"]),
                point_ids=[],
                error="question_auto_tagger_unavailable",
            )
            for question in questions
        ]
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def run_one(question: dict[str, Any]) -> QuestionTaggingAIResult:
        async with semaphore:
            try:
                payload = await _request_single_question_tagging(
                    provider,
                    question=question,
                    knowledge_points=knowledge_points,
                    max_tokens=min(endpoint.max_tokens, 320),
                )
                point_ids = [int(item) for item in payload.get("knowledge_point_ids") or [] if str(item).strip()]
                return QuestionTaggingAIResult(
                    question_id=int(question["id"]),
                    point_ids=point_ids[:3],
                    confidence=_safe_confidence(payload.get("confidence")),
                    reason=_safe_text(payload.get("reason")),
                )
            except Exception as exc:
                return QuestionTaggingAIResult(
                    question_id=int(question["id"]),
                    point_ids=[],
                    error=str(exc)[:200],
                )

    return await asyncio.gather(*(run_one(question) for question in questions))


async def _request_single_question_tagging(
    provider: Any,
    *,
    question: dict[str, Any],
    knowledge_points: list[dict[str, Any]],
    max_tokens: int,
) -> dict[str, Any]:
    choices = "\n".join(
        f"{item['id']}\t{item['name']}"
        for item in knowledge_points
    )
    prompt = (
        "你是考试题考点标注助手。\n"
        "给定一道题和可选知识点，只返回最匹配的知识点结果。\n"
        "规则：\n"
        "1. 只从候选知识点里选择。\n"
        "2. 最多返回 3 个 knowledge_point_ids。\n"
        "3. 如果不确定，尽量只返回 1 个最相关的。\n"
        "4. reason 用极短中文，10个字以内。\n"
        "5. 只输出 JSON。\n\n"
        f"题目ID：{question['id']}\n"
        f"题型：{question.get('question_type') or ''}\n"
        f"题组导语：{question.get('group_stem') or ''}\n"
        f"共用材料：{question.get('material_text') or ''}\n"
        f"题干：{question.get('stem_text') or ''}\n"
        f"答案：{question.get('answer_text') or ''}\n"
        f"解析：{question.get('analysis_text') or ''}\n\n"
        "候选知识点：\n"
        f"{choices}"
    )
    schema = {
        "type": "object",
        "properties": {
            "knowledge_point_ids": {
                "type": "array",
                "items": {"type": "integer"},
            },
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["knowledge_point_ids", "confidence", "reason"],
    }
    try:
        payload = await provider.chat_json(
            [
                {"role": "system", "content": "只返回极简 JSON，不要解释。"},
                {"role": "user", "content": prompt},
            ],
            schema,
            max_tokens=max_tokens,
        )
    except Exception:
        text_response = await provider.chat(
            [
                {"role": "system", "content": "只输出编号，禁止解释。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=min(max_tokens, 80),
        )
        point_ids = _extract_point_ids(text_response, knowledge_points)
        return {
            "knowledge_point_ids": point_ids,
            "confidence": 0.8 if point_ids else None,
            "reason": "AI标注" if point_ids else None,
        }
    payload = payload if isinstance(payload, dict) else {}
    payload["knowledge_point_ids"] = _sanitize_point_ids(payload.get("knowledge_point_ids"), knowledge_points)
    payload["confidence"] = _safe_confidence(payload.get("confidence"))
    payload["reason"] = _safe_text(payload.get("reason")) or ("AI标注" if payload["knowledge_point_ids"] else None)
    return payload


def run_auto_tag_questions_with_ollama(
    *,
    questions: list[dict[str, Any]],
    knowledge_points: list[dict[str, Any]],
    concurrency: int = 5,
) -> list[QuestionTaggingAIResult]:
    return _run_async(
        auto_tag_questions_with_ollama(
            questions=questions,
            knowledge_points=knowledge_points,
            concurrency=concurrency,
        )
    )


def _get_auto_tagger_provider() -> tuple[Any | None, LLMEndpointConfig | None]:
    try:
        endpoint = get_llm_settings().question_auto_tagger
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


def _safe_confidence(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, numeric))


def _safe_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _extract_point_ids(text: str, knowledge_points: list[dict[str, Any]]) -> list[int]:
    valid_ids = {int(item["id"]) for item in knowledge_points}
    values = []
    for match in json.dumps(str(text or ""), ensure_ascii=False).split("\\n"):
        for token in match.replace(",", " ").replace("，", " ").split():
            if token.isdigit():
                point_id = int(token)
                if point_id in valid_ids and point_id not in values:
                    values.append(point_id)
    return values[:3]


def _sanitize_point_ids(value: Any, knowledge_points: list[dict[str, Any]]) -> list[int]:
    valid_ids = {int(item["id"]) for item in knowledge_points}
    values: list[int] = []
    for item in value or []:
        try:
            point_id = int(item)
        except (TypeError, ValueError):
            continue
        if point_id in valid_ids and point_id not in values:
            values.append(point_id)
    return values[:3]
