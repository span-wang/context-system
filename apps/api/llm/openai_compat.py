from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections.abc import Callable
from typing import Any

import httpx

from settings import LLMEndpointConfig, LLMTarget, llm_api_key_env_candidates, resolve_llm_api_key

OPENAI_COMPAT_TIMEOUT_SECONDS = 600
OLLAMA_NATIVE_TIMEOUT_SECONDS = 600
HTTP_RETRY_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504}
HTTP_RETRY_ATTEMPTS = 3
OllamaStreamCallback = Callable[[dict[str, Any]], None]
DIAGNOSTIC_RESPONSE_HEADERS = (
    "content-type",
    "server",
    "cf-ray",
    "x-request-id",
    "x-amzn-requestid",
    "via",
    "retry-after",
)
logger = logging.getLogger(__name__)


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
        response = await self._post_json_with_retries(
            f"{self.base_url}/chat/completions",
            headers=headers,
            payload=payload,
            timeout=OPENAI_COMPAT_TIMEOUT_SECONDS,
        )
        data = _parse_openai_compat_json_response(response, provider_label=_provider_label(self.is_deepseek))
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
            "think": not bool(getattr(self.config, "disable_thinking", False)),
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
            "think": not bool(getattr(self.config, "disable_thinking", False)),
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

    async def _post_json_with_retries(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: float,
    ) -> httpx.Response:
        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(1, HTTP_RETRY_ATTEMPTS + 1):
                try:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    return response
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    status_code = exc.response.status_code
                    if attempt >= HTTP_RETRY_ATTEMPTS or status_code not in HTTP_RETRY_STATUSES:
                        raise RuntimeError(
                            _format_http_error(
                                exc.response,
                                provider_label=_provider_label(self.is_deepseek),
                                attempts=attempt,
                            )
                        ) from exc
                    await asyncio.sleep(_retry_delay_seconds(attempt, exc.response.headers))
                except (httpx.TimeoutException, httpx.NetworkError, httpx.ProtocolError) as exc:
                    last_error = exc
                    if attempt >= HTTP_RETRY_ATTEMPTS:
                        raise RuntimeError(
                            _format_transport_error(
                                exc,
                                provider_label=_provider_label(self.is_deepseek),
                                attempts=attempt,
                            )
                        ) from exc
                    await asyncio.sleep(_retry_delay_seconds(attempt))
        if last_error is not None:
            raise RuntimeError(str(last_error)) from last_error
        raise RuntimeError("LLM request failed without an error payload")


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


def _provider_label(is_deepseek: bool) -> str:
    return "DeepSeek" if is_deepseek else "LLM"


def _parse_openai_compat_json_response(response: httpx.Response, *, provider_label: str) -> dict[str, Any]:
    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        response_text = response.text or ""
        content_type = (response.headers.get("content-type") or "").strip() or "unknown"
        if _looks_like_html_payload(response_text):
            _log_html_response(response, provider_label=provider_label, context="success response")
            raise RuntimeError(
                f"{provider_label} 接口返回了 HTML 页面而不是 JSON（HTTP {response.status_code}）：{_describe_html_error_response(response)}"
            ) from exc
        raise RuntimeError(
            f"{provider_label} 接口返回的不是有效 JSON（content-type: {content_type}）：{_preview_text(response_text) or 'empty response'}"
        ) from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"{provider_label} 接口返回了非对象 JSON：{type(data).__name__}")
    return data


def _format_http_error(response: httpx.Response, *, provider_label: str, attempts: int) -> str:
    status_code = response.status_code
    detail = _response_error_text(response, provider_label=provider_label)
    retry_note = f"，已重试 {attempts} 次" if attempts > 1 else ""
    if status_code == 429:
        return f"{provider_label} 接口限流（HTTP 429{retry_note}）：{detail}"
    if 500 <= status_code < 600:
        return f"{provider_label} 接口临时异常（HTTP {status_code}{retry_note}）：{detail}"
    return f"{provider_label} 接口请求失败（HTTP {status_code}{retry_note}）：{detail}"


def _format_transport_error(exc: Exception, *, provider_label: str, attempts: int) -> str:
    detail = str(exc).strip() or exc.__class__.__name__
    retry_note = f"，已重试 {attempts} 次" if attempts > 1 else ""
    return f"{provider_label} 接口网络异常{retry_note}：{detail}"


def _response_error_text(response: httpx.Response, *, provider_label: str | None = None) -> str:
    response_text = (response.text or "").strip()
    if response_text and _looks_like_html_payload(response_text):
        _log_html_response(response, provider_label=provider_label or "LLM", context="error response")
        return _describe_html_error_response(response)
    try:
        raw = response.json()
    except Exception:
        return response_text[:500] or response.reason_phrase or "unknown error"

    if isinstance(raw, dict):
        error = raw.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("detail") or error.get("type")
            if message:
                return str(message)
        for key in ("message", "detail", "error"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return json.dumps(raw, ensure_ascii=False)[:500]
    if isinstance(raw, list):
        return json.dumps(raw, ensure_ascii=False)[:500]
    return str(raw)[:500]


def _retry_delay_seconds(attempt: int, headers: httpx.Headers | None = None) -> float:
    retry_after = _retry_after_seconds(headers)
    if retry_after is not None:
        return max(0.0, min(retry_after, 15.0))
    return min(1.5 * attempt, 6.0)


def _retry_after_seconds(headers: httpx.Headers | None) -> float | None:
    if not headers:
        return None
    raw = headers.get("retry-after")
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _looks_like_html_payload(text: str) -> bool:
    preview = (text or "").lstrip().lower()
    return preview.startswith("<!doctype html") or preview.startswith("<html")


def _describe_html_error_response(response: httpx.Response) -> str:
    gateway_label = _gateway_label(response)
    if gateway_label == "Cloudflare":
        hint = "疑似 Cloudflare 返回的超时或错误页"
    elif gateway_label in {"Nginx", "OpenResty", "Envoy"}:
        hint = f"疑似 {gateway_label} 返回的超时或错误页"
    else:
        hint = "疑似上游网关或反向代理返回的超时或错误页"
    return (
        f"返回了 HTML 错误页，{hint}，不是模型 JSON。"
        f"请检查 base_url 是否直连 LLM API 接口源站，以及 Cloudflare/Nginx 等代理的超时与转发配置。"
        f"响应头：{_response_header_summary(response)}"
    )


def _gateway_label(response: httpx.Response) -> str:
    server = (response.headers.get("server") or "").strip().lower()
    via = (response.headers.get("via") or "").strip().lower()
    if response.headers.get("cf-ray") or "cloudflare" in server or "cloudflare" in via:
        return "Cloudflare"
    if "openresty" in server or "openresty" in via:
        return "OpenResty"
    if "nginx" in server or "nginx" in via:
        return "Nginx"
    if "envoy" in server or "envoy" in via:
        return "Envoy"
    return "Gateway"


def _response_header_summary(response: httpx.Response) -> str:
    parts: list[str] = []
    for name in DIAGNOSTIC_RESPONSE_HEADERS:
        value = (response.headers.get(name) or "").strip()
        if not value:
            continue
        parts.append(f"{name}={_preview_text(value, max_chars=120)}")
    return "; ".join(parts) or "none"


def _response_request_url(response: httpx.Response) -> str:
    request = getattr(response, "request", None)
    url = getattr(request, "url", None)
    return str(url) if url else "unknown"


def _log_html_response(response: httpx.Response, *, provider_label: str, context: str) -> None:
    logger.warning(
        "%s returned HTML instead of JSON (%s): status=%s url=%s headers=%s body_preview=%s",
        provider_label,
        context,
        response.status_code,
        _response_request_url(response),
        _response_header_summary(response),
        _preview_text(response.text or ""),
    )


def _preview_text(text: str, *, max_chars: int = 240) -> str:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[: max_chars - 3].rstrip()}..."
