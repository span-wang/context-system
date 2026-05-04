from __future__ import annotations

from settings import LLMEndpointConfig, LLMTarget

from .anthropic import AnthropicProvider
from .base import LLMProvider
from .openai_compat import OpenAICompatProvider


def get_llm_provider(config: LLMEndpointConfig, target: LLMTarget | None = None) -> LLMProvider:
    provider = config.provider.strip()
    if provider in {"openai_compat", "deepseek"}:
        return OpenAICompatProvider(config, target)
    if provider == "anthropic":
        return AnthropicProvider(config, target)
    raise RuntimeError(f"unsupported llm provider: {config.provider}")
