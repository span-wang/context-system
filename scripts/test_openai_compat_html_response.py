from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from llm.openai_compat import _parse_openai_compat_json_response  # noqa: E402


class OpenAICompatHtmlResponseTests(unittest.TestCase):
    def test_html_response_surfaces_gateway_diagnostics_without_raw_html(self) -> None:
        response = httpx.Response(
            200,
            headers={
                "content-type": "text/html; charset=utf-8",
                "server": "cloudflare",
                "cf-ray": "abc123",
            },
            request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"),
            text="<!doctype html><html><body>Gateway Home</body></html>",
        )

        with patch("llm.openai_compat.logger.warning") as warning:
            with self.assertRaises(RuntimeError) as ctx:
                _parse_openai_compat_json_response(response, provider_label="LLM")

        message = str(ctx.exception)
        self.assertIn("返回了 HTML 页面而不是 JSON", message)
        self.assertIn("疑似 Cloudflare 返回的超时或错误页", message)
        self.assertIn("server=cloudflare", message)
        self.assertIn("cf-ray=abc123", message)
        self.assertNotIn("<!doctype html>", message.lower())
        warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
