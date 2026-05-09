from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from typing import Any

import httpx

from settings import LLMEndpointConfig, LLMTarget, llm_api_key_env_candidates, resolve_llm_api_key

OLLAMA_NATIVE_TIMEOUT_SECONDS = 600
OllamaStreamCallback = Callable[[dict[str, Any]], None]


class OpenAICompatProvider:
    def __init__(self, config: LLMEndpointConfig, target: LLMTarget | None = None) -> None:
        self.config = config
        configured_base_url = config.base_url or os.getenv("OPENAI_BASE_URL")
        if config.provider == "deepseek":
            default_base_url = "https://api.deepseek.com"
        else:
            default_base_url = "https://api.openai.com/v1"
        self.base_url = (configured_base_url or default_base_url).rstrip("/")
        self.is_deepseek = config.provider == "deepseek" or "api.deepseek.com" in self.base_url.lower()
        self.api_key = resolve_llm_api_key(config, target)
        self.api_key_env_candidates = llm_api_key_env_candidates(config, target)
        self.allow_missing_api_key = _allows_missing_api_key(config, target, self.base_url)
        self.use_ollama_native_chat = _uses_ollama_native_chat(config, target, self.base_url)
        self.ollama_native_base_url = _to_ollama_native_base_url(self.base_url) if self.use_ollama_native_chat else ""
        if "api.deepseek.com" in self.base_url.lower() and self.base_url.endswith("/v1"):
            self.base_url = self.base_url[:-3]

    async def chat(self, messages: list[dict], **kwargs: Any) -> str:
        if self.use_ollama_native_chat:
            return await self._chat_via_ollama_native(messages, **kwargs)
        if not self.api_key and not self.allow_missing_api_key:
            raise RuntimeError(_missing_key_message(self.is_deepseek, self.api_key_env_candidates))
        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
        }
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def chat_json(self, messages: list[dict], schema: dict, **kwargs: Any) -> dict:
        import json

        if self.use_ollama_native_chat:
            return await self._chat_json_via_ollama_native(messages, schema, **kwargs)

        payload_messages = messages + [
            {
                "role": "system",
                "content": f"Return only valid JSON matching this JSON Schema: {json.dumps(schema, ensure_ascii=False)}",
            }
        ]
        text = await self.chat(payload_messages, **kwargs)
        return json.loads(text)

    async def _chat_via_ollama_native(self, messages: list[dict], **kwargs: Any) -> str:
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": str(item.get("role") or "user"), "content": str(item.get("content") or "")}
                for item in messages
            ],
            "stream": False,
            "keep_alive": 0,
            "options": {
                "temperature": 0,
                "num_predict": int(kwargs.get("max_tokens", self.config.max_tokens)),
            },
        }
        content, thinking = await self._stream_ollama_native_response(
            payload,
            stream_callback=_coerce_stream_callback(kwargs.get("stream_callback")),
        )
        return content or thinking

    async def _chat_json_via_ollama_native(self, messages: list[dict], schema: dict, **kwargs: Any) -> dict:
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": str(item.get("role") or "user"), "content": str(item.get("content") or "")}
                for item in messages
            ],
            "stream": False,
            "keep_alive": 0,
            "format": schema,
            "options": {
                "temperature": 0,
                "num_predict": int(kwargs.get("max_tokens", self.config.max_tokens)),
            },
        }
        content, thinking = await self._stream_ollama_native_response(
            payload,
            stream_callback=_coerce_stream_callback(kwargs.get("stream_callback")),
        )
        response_text = content or thinking
        return json.loads(_extract_json_payload(response_text))

    async def _stream_ollama_native_response(
        self,
        payload: dict[str, Any],
        *,
        stream_callback: OllamaStreamCallback | None = None,
    ) -> tuple[str, str]:
        content_text = ""
        thinking_text = ""
        stream_payload = dict(payload)
        stream_payload["stream"] = True
        async with httpx.AsyncClient(timeout=OLLAMA_NATIVE_TIMEOUT_SECONDS) as client:
            async with client.stream(
                "POST",
                f"{self.ollama_native_base_url}/api/chat",
                json=stream_payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    message = chunk.get("message") if isinstance(chunk, dict) else {}
                    delta_content = str((message or {}).get("content") or "")
                    delta_thinking = str((message or {}).get("thinking") or "")
                    if delta_content:
                        content_text += delta_content
                    if delta_thinking:
                        thinking_text += delta_thinking
                    if stream_callback is not None:
                        stream_callback(
                            {
                                "delta_content": delta_content,
                                "delta_thinking": delta_thinking,
                                "content": content_text,
                                "thinking": thinking_text,
                                "done": bool(chunk.get("done")),
                                "done_reason": str(chunk.get("done_reason") or ""),
                            }
                        )
        return content_text.strip(), thinking_text.strip()


def _allows_missing_api_key(config: LLMEndpointConfig, target: LLMTarget | None, base_url: str) -> bool:
    normalized = (base_url or "").strip().lower()
    if config.provider.strip() != "openai_compat":
        return False
    return any(
        marker in normalized
        for marker in (
            "127.0.0.1:11434",
            "localhost:11434",
            "0.0.0.0:11434",
            "::1:11434",
        )
    )


def _uses_ollama_native_chat(config: LLMEndpointConfig, target: LLMTarget | None, base_url: str) -> bool:
    normalized = (base_url or "").strip().lower()
    if config.provider.strip() != "openai_compat":
        return False
    return any(
        marker in normalized
        for marker in (
            "127.0.0.1:11434",
            "localhost:11434",
            "0.0.0.0:11434",
            "::1:11434",
        )
    )


def _to_ollama_native_base_url(base_url: str) -> str:
    normalized = (base_url or "").rstrip("/")
    if normalized.endswith("/v1"):
        return normalized[:-3]
    return normalized


def _coerce_stream_callback(value: Any) -> OllamaStreamCallback | None:
    return value if callable(value) else None


def _extract_json_payload(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        return cleaned[start : end + 1]
    return cleaned


def _missing_key_message(is_deepseek: bool, env_keys: tuple[str, ...]) -> str:
    candidates = ", ".join(env_keys) if env_keys else "provider environment variables"
    if is_deepseek:
        return f"endpoint api_key or one of {candidates} in .env.local/.env/.evn/config.yaml is not configured"
    return f"endpoint api_key or {candidates} is not configured"
