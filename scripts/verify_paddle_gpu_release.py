from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one PaddleOCR pass and report GPU memory before/after release.")
    parser.add_argument("pdf_path", help="Path to a PDF file used for the OCR smoke test.")
    parser.add_argument("--max-pages", type=int, default=1, help="Number of pages to OCR.")
    parser.add_argument("--wait-seconds", type=float, default=2.0, help="Seconds to wait before the final GPU sample.")
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path).resolve()
    if not pdf_path.exists():
        raise SystemExit(f"PDF file not found: {pdf_path}")

    repo_root = Path(__file__).resolve().parents[1]
    api_root = repo_root / "apps" / "api"
    sys.path.insert(0, str(api_root))

    before = _gpu_memory()

    from library.pdf_ocr_pipeline import OCRPipelineOptions, run_pdf_ocr_pipeline

    result = run_pdf_ocr_pipeline(
        pdf_path.read_bytes(),
        pdf_path.name,
        options=OCRPipelineOptions(force_ocr=True, max_pages=max(1, args.max_pages)),
    )

    after_release = _gpu_memory()
    time.sleep(max(0.0, args.wait_seconds))
    after_wait = _gpu_memory()

    print(
        json.dumps(
            {
                "input": str(pdf_path),
                "provider": result.provider,
                "used_ocr": result.used_ocr,
                "page_count": len(result.pages),
                "gpu_memory": {
                    "before": before,
                    "after_release": after_release,
                    "after_wait": after_wait,
                },
                "warnings": result.warnings,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _gpu_memory() -> dict[str, int | str] | None:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.free,memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None

    line = completed.stdout.strip().splitlines()[0] if completed.stdout.strip() else ""
    parts = [part.strip() for part in line.split(",")]
    if len(parts) < 3:
        return {"raw": line}
    return {
        "used_mb": int(parts[0]),
        "free_mb": int(parts[1]),
        "total_mb": int(parts[2]),
    }


if __name__ == "__main__":
    raise SystemExit(main())
