from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.papers import _split_paper_sections  # noqa: E402


class PaperParserPromptFragmentTests(unittest.TestCase):
    def test_splits_prompt_fragments_without_options(self) -> None:
        text = """
不定项选择题
根据资料①，下列各项中，会计处理正确的是（）。
借：库存商品 10
贷：原材料 10
根据资料②，下列各项中，表述正确的是（）。
综上，本题应选AC
""".strip()
        section = _split_paper_sections(None, text)[0]

        self.assertEqual(len(section.blocks), 2)
        self.assertTrue(section.blocks[0].raw_text.startswith("根据资料①"))
        self.assertTrue(section.blocks[1].raw_text.startswith("根据资料②"))


if __name__ == "__main__":
    unittest.main()
