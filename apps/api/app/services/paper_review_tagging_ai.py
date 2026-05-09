from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass
from typing import Any

from llm.providers import get_llm_provider
from settings import LLMEndpointConfig


OLLAMA_QWEN3_VL_8B_ENDPOINT = LLMEndpointConfig(
    provider="openai_compat",
    model="qwen3-vl:8b",
    max_tokens=600,
    base_url="http://127.0.0.1:11434/v1",
    api_key=None,
)


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
    provider = get_llm_provider(OLLAMA_QWEN3_VL_8B_ENDPOINT, target="reviewer")
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def run_one(question: dict[str, Any]) -> QuestionTaggingAIResult:
        async with semaphore:
            try:
                payload = await _request_single_question_tagging(
                    provider,
                    question=question,
                    knowledge_points=knowledge_points,
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
) -> dict[str, Any]:
    choices = "\n".join(
        f"{item['id']}\t{item['name']}"
        for item in knowledge_points
    )
    prompt = (
        "你是考试题考点标注助手。\n"
        "给定一道题和可选知识点，只返回最匹配的知识点 id。\n"
        "这是思考模型，但最终只输出极简 JSON，不要解释过程。\n"
        "规则：\n"
        "1. 只从候选知识点里选择。\n"
        "2. 最多返回 3 个 knowledge_point_ids。\n"
        "3. 如果不确定，尽量只返回 1 个最相关的。\n"
        "4. reason 用极短中文，10 个字以内。\n"
        "5. 只输出 JSON。\n\n"
        f"题目ID：{question['id']}\n"
        f"题型：{question.get('question_type') or ''}\n"
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
    return await _chat_json(
        provider,
        system_prompt="只返回极简 JSON 结果。",
        user_prompt=prompt,
        schema=schema,
        max_tokens=400,
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
    cleaned = str(text or "").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        return cleaned[start : end + 1]
    return cleaned


def _safe_confidence(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, numeric))


def _safe_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
