from __future__ import annotations

from typing import Any

import httpx

from settings import LLMEndpointConfig, LLMTarget, resolve_llm_api_key


class AnthropicProvider:
    def __init__(self, config: LLMEndpointConfig, target: LLMTarget | None = None) -> None:
        self.config = config
        self.api_key = resolve_llm_api_key(config, target)

    async def chat(self, messages: list[dict], **kwargs: Any) -> str:
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured")
        payload = {
            "model": self.config.model,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": messages,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
        data = response.json()
        blocks = data.get("content", [])
        return "\n".join(block.get("text", "") for block in blocks if block.get("type") == "text")

    async def chat_json(self, messages: list[dict], schema: dict, **kwargs: Any) -> dict:
        import json

        text = await self.chat(messages, **kwargs)
        return json.loads(text)
