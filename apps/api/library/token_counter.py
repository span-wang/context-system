from __future__ import annotations

from math import ceil


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        chinese_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
        other_chars = max(0, len(text) - chinese_chars)
        return chinese_chars + ceil(other_chars / 4)


def estimate_sources_tokens(texts: list[str], user_notes: str | None = None) -> int:
    return sum(estimate_tokens(text) for text in texts) + estimate_tokens(user_notes or "")

