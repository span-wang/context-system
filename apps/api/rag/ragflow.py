from __future__ import annotations

import httpx

from schemas.context import ContextSource
from settings import RAGFlowConfig


class RAGFlowProvider:
    def __init__(self, config: RAGFlowConfig) -> None:
        self.config = config

    async def retrieve(
        self,
        query: str,
        dataset_ids: list[str],
        filters: dict,
        top_k: int = 8,
    ) -> list[ContextSource]:
        if not self.config.enabled or not dataset_ids:
            return []
        headers = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        payload = {
            "question": query,
            "dataset_ids": dataset_ids,
            "top_k": top_k,
            "filters": filters,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.config.base_url.rstrip('/')}/api/v1/retrieval",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
        raw = response.json()
        chunks = raw.get("data", {}).get("chunks") or raw.get("chunks") or raw.get("data") or []
        sources: list[ContextSource] = []
        for index, chunk in enumerate(chunks[:top_k]):
            text = chunk.get("content") or chunk.get("text") or chunk.get("chunk") or ""
            if not text:
                continue
            doc_name = chunk.get("document_name") or chunk.get("doc_name") or "RAGFlow"
            sources.append(
                ContextSource(
                    text=text,
                    source_label=f"RAGFlow:{doc_name}",
                    source_type=chunk.get("source_type") or "unknown",
                    authority=chunk.get("authority") or "unknown",
                    chunk_id=str(chunk.get("id") or chunk.get("chunk_id") or index),
                    page=chunk.get("page"),
                )
            )
        return sources

