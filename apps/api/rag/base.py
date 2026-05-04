from typing import Protocol

from schemas.context import ContextSource


class RAGProvider(Protocol):
    async def retrieve(
        self,
        query: str,
        dataset_ids: list[str],
        filters: dict,
        top_k: int = 8,
    ) -> list[ContextSource]: ...

