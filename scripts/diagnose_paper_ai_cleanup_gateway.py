from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from llm.providers import get_llm_provider  # noqa: E402
from settings import get_settings  # noqa: E402
from app.services.paper_ai_cleanup import _request_ai_cleanup  # noqa: E402


def _preview(value: Any, limit: int = 200) -> str:
    text = str(value or "").strip().replace("\r", " ").replace("\n", " ")
    return text[:limit]


async def _run_case(name: str, fn) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = await fn()
        elapsed = round(time.perf_counter() - started, 2)
        return {"case": name, "ok": True, "elapsed_seconds": elapsed, "result": result}
    except Exception as exc:
        elapsed = round(time.perf_counter() - started, 2)
        return {
            "case": name,
            "ok": False,
            "elapsed_seconds": elapsed,
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        }


async def main() -> None:
    settings = get_settings()
    endpoint = settings.paper_ai_cleanup
    provider = get_llm_provider(endpoint, target="reviewer")

    nested_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "score": {"type": "number"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["name", "score", "tags"],
                },
            },
        },
        "required": ["title", "items"],
    }

    sample_text = (
        "一、单项选择题\n"
        "1. 下列关于会计要素的表述中，正确的是（ ）。\n"
        "A. 资产是过去的交易形成的现时义务\n"
        "B. 负债会导致经济利益流入企业\n"
        "C. 所有者权益是企业资产扣除负债后由所有者享有的剩余权益\n"
        "D. 收入一定表现为货币资金增加\n"
        "答案：C\n"
        "解析：所有者权益是企业资产扣除负债后由所有者享有的剩余权益。"
    )

    cases = [
        (
            "plain_chat",
            lambda: provider.chat(
                [
                    {"role": "system", "content": "你是一个简洁助手。"},
                    {"role": "user", "content": "只回复 OK"},
                ],
                max_tokens=16,
            ),
        ),
        (
            "flat_json",
            lambda: provider.chat_json(
                [
                    {"role": "system", "content": "你是一个只返回 JSON 的助手。"},
                    {"role": "user", "content": "返回 {\"status\":\"ok\",\"value\":1} 对应的数据。"},
                ],
                {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "value": {"type": "number"},
                    },
                    "required": ["status", "value"],
                },
                max_tokens=64,
            ),
        ),
        (
            "nested_json",
            lambda: provider.chat_json(
                [
                    {"role": "system", "content": "你是一个只返回 JSON 的助手。"},
                    {
                        "role": "user",
                        "content": "返回一个标题为 demo，包含 2 个对象数组 items，每个对象有 name、score、tags。",
                    },
                ],
                nested_schema,
                max_tokens=256,
            ),
        ),
        (
            "paper_cleanup_request",
            lambda: _request_ai_cleanup(
                provider,
                sample_text,
                endpoint=endpoint,
                paper_name="联调测试卷",
                subject_name="初级会计",
                category_name="实务",
                chunk_index=1,
                chunk_count=1,
            ),
        ),
    ]

    outputs: list[dict[str, Any]] = []
    for name, fn in cases:
        result = await _run_case(name, fn)
        if result.get("ok"):
            payload = result.get("result")
            if name == "plain_chat":
                result["preview"] = _preview(payload)
            elif isinstance(payload, dict):
                result["preview"] = _preview(json.dumps(payload, ensure_ascii=False))
                if name == "paper_cleanup_request":
                    result["question_count"] = ((payload.get("prediction") or {}).get("question_count"))
                    result["section_count"] = len(((payload.get("prediction") or {}).get("sections") or []))
            result.pop("result", None)
        outputs.append(result)

    summary = {
        "endpoint": {
            "provider": endpoint.provider,
            "model": endpoint.model,
            "base_url": endpoint.base_url,
            "max_tokens": endpoint.max_tokens,
            "disable_thinking": getattr(endpoint, "disable_thinking", None),
        },
        "results": outputs,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
