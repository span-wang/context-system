from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.papers import _build_ai_split_failure_detail  # noqa: E402


class PaperParseFailureDetailTests(unittest.TestCase):
    def test_prefers_upstream_ai_error(self) -> None:
        detail = _build_ai_split_failure_detail(
            SimpleNamespace(
                error="LLM 接口临时异常（HTTP 524）：Receive timeout from origin",
                warnings=["AI 清噪第 1/1 段失败，已回退规则清噪：..."],
            )
        )

        self.assertEqual(detail, "AI 切题失败：LLM 接口临时异常（HTTP 524）：Receive timeout from origin")

    def test_falls_back_to_first_warning(self) -> None:
        detail = _build_ai_split_failure_detail(
            SimpleNamespace(
                error=None,
                warnings=["AI 清噪第 1/1 段失败，已回退规则清噪：示例错误", "其他提示"],
            )
        )

        self.assertEqual(detail, "AI 切题失败：AI 清噪第 1/1 段失败，已回退规则清噪：示例错误")

    def test_uses_generic_detail_when_no_error_or_warning(self) -> None:
        detail = _build_ai_split_failure_detail(SimpleNamespace(error=None, warnings=[]))

        self.assertEqual(detail, "AI 切题未生成有效结果")


if __name__ == "__main__":
    unittest.main()
