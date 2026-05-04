from __future__ import annotations

import os
from typing import Any

import httpx

from settings import LLMEndpointConfig


class OpenAICompatProvider:
    def __init__(self, config: LLMEndpointConfig) -> None:
        self.config = config
        if config.provider == "deepseek":
            self.api_key = config.api_key or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
            default_base_url = "https://api.deepseek.com"
        else:
            self.api_key = config.api_key or os.getenv("OPENAI_API_KEY")
            default_base_url = "https://api.openai.com/v1"
        self.base_url = (config.base_url or os.getenv("OPENAI_BASE_URL") or default_base_url).rstrip("/")
        if "api.deepseek.com" in self.base_url.lower() and self.base_url.endswith("/v1"):
            self.base_url = self.base_url[:-3]

    async def chat(self, messages: list[dict], **kwargs: Any) -> str:
        if not self.api_key:
            raise RuntimeError("endpoint api_key, DEEPSEEK_API_KEY, or OPENAI_API_KEY is not configured")
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
