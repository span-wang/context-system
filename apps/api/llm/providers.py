from __future__ import annotations

from settings import LLMEndpointConfig

from .anthropic import AnthropicProvider
from .base import LLMProvider
from .openai_compat import OpenAICompatProvider


def get_llm_provider(config: LLMEndpointConfig) -> LLMProvider:
    provider = config.provider.strip()
    if provider in {"openai_compat", "deepseek"}:
        return OpenAICompatProvider(config)
    if provider == "anthropic":
        return AnthropicProvider(config)
    raise RuntimeError(f"unsupported llm provider: {config.provider}")
