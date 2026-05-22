from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

import paddle

import library.parser as parser_module


class VL15RuntimeTests(unittest.TestCase):
    def test_prepare_local_paddleocr_vl15_env_forces_dynamic_mode(self) -> None:
        original_dynamic_mode = paddle.in_dynamic_mode()
        original_patch = parser_module._patch_paddle_bfloat16_support
        parser_module._patch_paddle_bfloat16_support = lambda device: None

        try:
            paddle.enable_static()
            self.assertFalse(paddle.in_dynamic_mode())

            parser_module._prepare_local_paddleocr_vl15_env(
                {
                    "device": "cpu",
                    "cache_home": Path.cwd(),
                    "model_source": "modelscope",
                    "disable_model_source_check": True,
                }
            )

            self.assertTrue(paddle.in_dynamic_mode())
        finally:
            parser_module._patch_paddle_bfloat16_support = original_patch
            if original_dynamic_mode:
                paddle.disable_static()
            else:
                paddle.enable_static()


if __name__ == "__main__":
    unittest.main()
