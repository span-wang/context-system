from typing import Any, Protocol


class LLMProvider(Protocol):
    async def chat(self, messages: list[dict], **kwargs: Any) -> str: ...

    async def chat_json(self, messages: list[dict], schema: dict, **kwargs: Any) -> dict: ...

