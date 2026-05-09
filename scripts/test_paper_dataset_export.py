from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.paper_dataset import export_paper_parser_sample  # noqa: E402


class PaperDatasetExportTests(unittest.TestCase):
    def test_export_sample_writes_expected_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir)
            sample_dir = export_paper_parser_sample(
                paper_id=123,
                paper_name="Sample Paper",
                source_text="1. 下列说法正确的是？\nA. 选项一\n答案：A\n解析：示例解析",
                output_root=output_root,
            )

            self.assertEqual(sample_dir.parent, output_root)
            self.assertTrue((sample_dir / "source.txt").exists())
            self.assertTrue((sample_dir / "meta.json").exists())
            self.assertTrue((sample_dir / "prediction.json").exists())
            self.assertTrue((sample_dir / "gold.template.json").exists())
            self.assertTrue((sample_dir / "gold.json").exists())

            meta = json.loads((sample_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(Path(str(meta["export_root"])).resolve(), output_root.resolve())

    def test_export_sample_copies_markdown_images(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "dataset"
            markdown_root = Path(temp_dir) / "markdown_assets"
            image_path = markdown_root / "imgs" / "page_0001" / "demo.jpg"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (12, 8), color="white").save(image_path)

            sample_dir = export_paper_parser_sample(
                paper_id=124,
                paper_name="Image Paper",
                source_text='1. 示例题干 <div><img src="imgs/page_0001/demo.jpg" /></div>',
                markdown_image_roots=[str(markdown_root)],
                output_root=output_root,
            )

            self.assertTrue((sample_dir / "imgs" / "page_0001" / "demo.jpg").exists())


if __name__ == "__main__":
    unittest.main()
