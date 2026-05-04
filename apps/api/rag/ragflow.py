from __future__ import annotations

from typing import Any

import httpx

from schemas.context import ContextSource
from settings import RAGFlowConfig


class RAGFlowAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class RAGFlowProvider:
    def __init__(self, config: RAGFlowConfig) -> None:
        self.config = config

    async def list_datasets(
        self,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        if not self.config.enabled:
            return {"datasets": [], "total": 0}

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                self._url("/api/v1/datasets"),
                params={
                    "page": page,
                    "page_size": page_size,
                },
                headers=self._headers(),
            )
            self._raise_for_status(response, "拉取 dataset 清单")

        raw = response.json()
        self._raise_for_ragflow_code(raw, "拉取 dataset 清单")
        raw_datasets = raw.get("data", []) if isinstance(raw, dict) else []
        if isinstance(raw_datasets, dict):
            raw_datasets = raw_datasets.get("datasets") or raw_datasets.get("items") or []
        datasets = [
            self._normalize_dataset(item)
            for item in raw_datasets
            if isinstance(item, dict) and item.get("id")
        ]
        return {
            "datasets": datasets,
            "total": raw.get("total_datasets") or raw.get("total") or len(datasets) if isinstance(raw, dict) else len(datasets),
        }

    async def retrieve(
        self,
        query: str,
        dataset_ids: list[str],
        filters: dict,
        top_k: int = 8,
    ) -> list[ContextSource]:
        if not self.config.enabled or not dataset_ids:
            return []
        payload = {
            "question": query,
            "dataset_ids": dataset_ids,
            "top_k": top_k,
            "filters": filters,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                self._url("/api/v1/retrieval"),
                json=payload,
                headers=self._headers(),
            )
            self._raise_for_status(response, "检索")
        raw = response.json()
        self._raise_for_ragflow_code(raw, "检索")
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

    def _url(self, path: str) -> str:
        return f"{self.config.base_url.rstrip('/')}{path}"

    def _headers(self) -> dict[str, str]:
        api_key = (self.config.api_key or "").strip()
        if not api_key:
            raise RAGFlowAPIError(
                "RAGFlow API Key 未配置：请在 .evn/.env.local 中设置 RAGFLOW_KEY，或在 config.yaml 的 ragflow.api_key 配置。",
                status_code=422,
            )
        return {"Authorization": f"Bearer {api_key}"}

    def _raise_for_status(self, response: httpx.Response, action: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = self._response_error_text(response)
            if response.status_code == 401:
                raise RAGFlowAPIError(
                    "RAGFlow 认证失败（401）：请检查 RAGFLOW_KEY 是否正确、未过期，并且是否属于当前 RAGFlow 地址。",
                    status_code=401,
                ) from exc
            if response.status_code == 403:
                raise RAGFlowAPIError(
                    f"RAGFlow {action}被拒绝（403）：当前 API Key 没有权限访问这些 dataset。",
                    status_code=403,
                ) from exc
            raise RAGFlowAPIError(f"RAGFlow {action}失败（HTTP {response.status_code}）：{detail}") from exc

    def _raise_for_ragflow_code(self, raw: Any, action: str) -> None:
        if not isinstance(raw, dict):
            return
        code = raw.get("code")
        if code not in (None, 0):
            message = raw.get("message") or raw.get("detail") or f"code={code}"
            raise RAGFlowAPIError(f"RAGFlow {action}失败：{message}")

    def _response_error_text(self, response: httpx.Response) -> str:
        try:
            raw = response.json()
            if isinstance(raw, dict):
                return str(raw.get("message") or raw.get("detail") or raw)
            return str(raw)
        except Exception:
            return response.text[:500] or response.reason_phrase

    def _normalize_dataset(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(item.get("id")),
            "name": item.get("name") or item.get("id"),
            "description": item.get("description"),
            "document_count": item.get("document_count"),
            "chunk_count": item.get("chunk_count"),
            "token_num": item.get("token_num"),
            "status": item.get("status"),
            "permission": item.get("permission"),
            "embedding_model": item.get("embedding_model"),
            "chunk_method": item.get("chunk_method"),
            "unstart_count": item.get("unstart_count"),
            "running_count": item.get("running_count"),
            "cancel_count": item.get("cancel_count"),
            "done_count": item.get("done_count"),
            "fail_count": item.get("fail_count"),
        }
