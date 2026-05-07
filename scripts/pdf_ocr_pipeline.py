from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean PDF noise, run OCR, and export structured outputs.")
    parser.add_argument("pdf_path", help="Path to the input PDF file.")
    parser.add_argument(
        "--output-dir",
        default="output/pdf_ocr",
        help="Directory where JSON/Markdown/TXT outputs will be written.",
    )
    parser.add_argument(
        "--options-json",
        default=None,
        help="Optional JSON string or JSON-like Python dict string for OCRPipelineOptions overrides.",
    )
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Print the structured JSON payload to stdout after processing.",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path).resolve()
    if not pdf_path.exists():
        raise SystemExit(f"PDF file not found: {pdf_path}")

    repo_root = Path(__file__).resolve().parents[1]
    api_root = repo_root / "apps" / "api"
    sys.path.insert(0, str(api_root))

    from library.pdf_ocr_pipeline import load_pipeline_options, run_pdf_ocr_pipeline, write_pipeline_outputs

    options = load_pipeline_options(args.options_json)
    result = run_pdf_ocr_pipeline(pdf_path.read_bytes(), pdf_path.name, options=options)
    outputs = write_pipeline_outputs(result, Path(args.output_dir).resolve())

    summary = {
        "input": str(pdf_path),
        "provider": result.provider,
        "used_ocr": result.used_ocr,
        "page_count": len(result.pages),
        "warnings": result.warnings,
        "outputs": {name: str(path) for name, path in outputs.items()},
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.print_json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
