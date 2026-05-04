from __future__ import annotations

import os
from typing import Any

import httpx

from settings import LLMEndpointConfig, LLMTarget, llm_api_key_env_candidates, resolve_llm_api_key


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
        if "api.deepseek.com" in self.base_url.lower() and self.base_url.endswith("/v1"):
            self.base_url = self.base_url[:-3]

    async def chat(self, messages: list[dict], **kwargs: Any) -> str:
        if not self.api_key:
            raise RuntimeError(_missing_key_message(self.is_deepseek, self.api_key_env_candidates))
        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def chat_json(self, messages: list[dict], schema: dict, **kwargs: Any) -> dict:
        import json

        payload_messages = messages + [
            {
                "role": "system",
                "content": f"Return only valid JSON matching this JSON Schema: {json.dumps(schema, ensure_ascii=False)}",
            }
        ]
        text = await self.chat(payload_messages, **kwargs)
        return json.loads(text)


def _missing_key_message(is_deepseek: bool, env_keys: tuple[str, ...]) -> str:
    candidates = ", ".join(env_keys) if env_keys else "provider environment variables"
    if is_deepseek:
        return f"endpoint api_key or one of {candidates} in .env.local/.env/.evn/config.yaml is not configured"
    return f"endpoint api_key or {candidates} is not configured"
