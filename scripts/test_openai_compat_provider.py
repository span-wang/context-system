from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from llm.openai_compat import HTTP_RETRY_ATTEMPTS, OpenAICompatProvider  # noqa: E402
from settings import LLMEndpointConfig  # noqa: E402


class _FakeAsyncClient:
    def __init__(self, responses: list[httpx.Response | Exception], *args, **kwargs) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, headers: dict[str, str] | None = None, json: dict | None = None) -> httpx.Response:
        self.calls.append({"url": url, "headers": headers or {}, "json": json or {}})
        if not self._responses:
            raise AssertionError("No fake responses left for httpx.AsyncClient.post")
        next_item = self._responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item


def _response(
    status_code: int,
    *,
    json_body: dict | None = None,
    text: str = "",
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    if json_body is not None:
        return httpx.Response(status_code, json=json_body, headers=headers, request=request)
    return httpx.Response(status_code, text=text, headers=headers, request=request)


class OpenAICompatProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_transient_500_then_succeeds(self) -> None:
        fake_client = _FakeAsyncClient(
            [
                _response(500, json_body={"error": {"message": "Internal Server Error"}}),
                _response(200, json_body={"choices": [{"message": {"content": "ok"}}]}),
            ]
        )
        provider = OpenAICompatProvider(
            LLMEndpointConfig(
                provider="deepseek",
                model="deepseek-chat",
                max_tokens=1024,
                api_key="test-key",
                base_url="https://api.deepseek.com/v1",
            )
        )

        with patch("llm.openai_compat.httpx.AsyncClient", return_value=fake_client):
            with patch("llm.openai_compat.asyncio.sleep", new=AsyncMock()):
                content = await provider.chat([{"role": "user", "content": "hello"}])

        self.assertEqual(content, "ok")
        self.assertEqual(len(fake_client.calls), 2)

    async def test_reports_friendly_error_after_retry_exhaustion(self) -> None:
        fake_client = _FakeAsyncClient(
            [
                _response(500, json_body={"error": {"message": "Internal Server Error"}})
                for _ in range(HTTP_RETRY_ATTEMPTS)
            ]
        )
        provider = OpenAICompatProvider(
            LLMEndpointConfig(
                provider="deepseek",
                model="deepseek-chat",
                max_tokens=1024,
                api_key="test-key",
                base_url="https://api.deepseek.com/v1",
            )
        )

        with patch("llm.openai_compat.httpx.AsyncClient", return_value=fake_client):
            with patch("llm.openai_compat.asyncio.sleep", new=AsyncMock()):
                with self.assertRaises(RuntimeError) as context:
                    await provider.chat([{"role": "user", "content": "hello"}])

        message = str(context.exception)
        self.assertIn("DeepSeek 接口临时异常", message)
        self.assertIn("HTTP 500", message)
        self.assertIn(f"已重试 {HTTP_RETRY_ATTEMPTS} 次", message)
        self.assertEqual(len(fake_client.calls), HTTP_RETRY_ATTEMPTS)

    async def test_reports_gateway_timeout_for_html_error_page(self) -> None:
        fake_client = _FakeAsyncClient(
            [
                _response(
                    504,
                    text="<!doctype html><html><body>Gateway timeout</body></html>",
                    headers={
                        "content-type": "text/html; charset=utf-8",
                        "server": "cloudflare",
                        "cf-ray": "ray-test",
                    },
                )
                for _ in range(HTTP_RETRY_ATTEMPTS)
            ]
        )
        provider = OpenAICompatProvider(
            LLMEndpointConfig(
                provider="deepseek",
                model="deepseek-chat",
                max_tokens=1024,
                api_key="test-key",
                base_url="https://api.deepseek.com/v1",
            )
        )

        with patch("llm.openai_compat.httpx.AsyncClient", return_value=fake_client):
            with patch("llm.openai_compat.asyncio.sleep", new=AsyncMock()):
                with patch("llm.openai_compat.logger.warning") as warning:
                    with self.assertRaises(RuntimeError) as context:
                        await provider.chat([{"role": "user", "content": "hello"}])

        message = str(context.exception)
        self.assertIn("DeepSeek 接口临时异常", message)
        self.assertIn("HTTP 504", message)
        self.assertIn(f"已重试 {HTTP_RETRY_ATTEMPTS} 次", message)
        self.assertIn("疑似 Cloudflare 返回的超时或错误页", message)
        self.assertIn("server=cloudflare", message)
        self.assertIn("cf-ray=ray-test", message)
        self.assertNotIn("<!doctype html>", message.lower())
        warning.assert_called_once()
        self.assertEqual(len(fake_client.calls), HTTP_RETRY_ATTEMPTS)


if __name__ == "__main__":
    unittest.main()
