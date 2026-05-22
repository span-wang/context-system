from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from generators.llm import _layout_user_prompt
from routers import generate as generate_router
from schemas.context import ContextSource, GenerationContext


def _build_context(layout_prompt: str) -> GenerationContext:
    return GenerationContext(
        mode="direct",
        subject="会计",
        category="基础",
        chapter="第一章",
        content_type="tri_color",
        options={"layout_prompt": layout_prompt, "layout_mode_name": "knowledge"},
        user_notes="突出真题和易错点",
        sources=[ContextSource(text="完整教材正文", source_label="官方教材")],
    )


class LayoutPromptDedupTests(unittest.TestCase):
    def test_layout_user_prompt_avoids_duplicate_source_blocks_for_self_contained_layout_prompt(self) -> None:
        layout_prompt = "\n".join(
            [
                "请输出小红书 Markdown。",
                "",
                "[Task Info]",
                "Subject: 会计",
                "",
                "[User Notes]",
                "突出真题和易错点",
                "",
                "[Library Sources]",
                "--- Source 1: 教材.md ---",
                "预览素材",
            ]
        )

        prompt = _layout_user_prompt(_build_context(layout_prompt), "会计 · 基础 · 第一章 · 三色笔记", layout_prompt)

        self.assertNotIn("学科：", prompt)
        self.assertNotIn("后端已解析/检索到的完整素材如下", prompt)
        self.assertNotIn("补充说明：", prompt)
        self.assertNotIn("完整教材正文", prompt)
        self.assertEqual(prompt.count("[Library Sources]"), 1)

    def test_layout_user_prompt_keeps_backend_fallback_for_plain_layout_prompt(self) -> None:
        layout_prompt = "请按知识卡片格式输出。"

        prompt = _layout_user_prompt(_build_context(layout_prompt), "会计 · 基础 · 第一章 · 三色笔记", layout_prompt)

        self.assertIn("补充说明：", prompt)
        self.assertIn("突出真题和易错点", prompt)
        self.assertIn("后端已解析/检索到的完整素材如下，请据此生成：", prompt)
        self.assertIn("[S1] 官方教材", prompt)
        self.assertIn("完整教材正文", prompt)

    def test_ensure_context_size_skips_source_double_count_for_self_contained_layout_prompt(self) -> None:
        captured: dict[str, object] = {}
        layout_prompt = "[Task Info]\nSubject: 会计\n\n[Library Sources]\n预览素材"

        def fake_estimate(texts: list[str], user_notes: str | None = None) -> int:
            captured["texts"] = texts
            captured["user_notes"] = user_notes
            return 12

        with patch.object(generate_router, "estimate_sources_tokens", side_effect=fake_estimate), patch.object(
            generate_router,
            "get_settings",
            return_value=SimpleNamespace(app=SimpleNamespace(context_token_limit=100)),
        ):
            generate_router._ensure_context_size(_build_context(layout_prompt))

        self.assertEqual(captured["texts"], [])
        self.assertEqual(captured["user_notes"], layout_prompt)

    def test_ensure_context_size_keeps_sources_for_plain_layout_prompt(self) -> None:
        captured: dict[str, object] = {}
        layout_prompt = "请按知识卡片格式输出。"

        def fake_estimate(texts: list[str], user_notes: str | None = None) -> int:
            captured["texts"] = texts
            captured["user_notes"] = user_notes
            return 12

        with patch.object(generate_router, "estimate_sources_tokens", side_effect=fake_estimate), patch.object(
            generate_router,
            "get_settings",
            return_value=SimpleNamespace(app=SimpleNamespace(context_token_limit=100)),
        ):
            generate_router._ensure_context_size(_build_context(layout_prompt))

        self.assertEqual(captured["texts"], ["完整教材正文"])
        self.assertEqual(captured["user_notes"], "突出真题和易错点\n请按知识卡片格式输出。")

    def test_ensure_context_size_keeps_sources_for_ragflow_preview_prompt(self) -> None:
        captured: dict[str, object] = {}
        layout_prompt = "[Task Info]\nSubject: 会计\n\n[RAGFlow Retrieval]\nDataset IDs: ds-1"

        def fake_estimate(texts: list[str], user_notes: str | None = None) -> int:
            captured["texts"] = texts
            captured["user_notes"] = user_notes
            return 12

        with patch.object(generate_router, "estimate_sources_tokens", side_effect=fake_estimate), patch.object(
            generate_router,
            "get_settings",
            return_value=SimpleNamespace(app=SimpleNamespace(context_token_limit=100)),
        ):
            generate_router._ensure_context_size(_build_context(layout_prompt))

        self.assertEqual(captured["texts"], ["完整教材正文"])
        self.assertEqual(captured["user_notes"], "突出真题和易错点\n[Task Info]\nSubject: 会计\n\n[RAGFlow Retrieval]\nDataset IDs: ds-1")


if __name__ == "__main__":
    unittest.main()
