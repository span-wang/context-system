from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify_paper_parser.py <sample_path> <api_root>")

    sample_path = Path(sys.argv[1]).resolve()
    api_root = Path(sys.argv[2]).resolve()
    sys.path.insert(0, str(api_root))

    from app.services.papers import _parse_question_block, _split_paper_sections

    text = sample_path.read_text(encoding="utf-8")
    sections = _split_paper_sections(None, text)
    payload: list[dict[str, object]] = []
    for section in sections:
        items: list[dict[str, object]] = []
        for block in section.blocks[:5]:
            parsed = _parse_question_block(block, section)
            items.append(
                {
                    "question_no": parsed.question_no,
                    "question_type": parsed.question_type,
                    "subquestion_count": parsed.subquestion_count,
                    "stem_preview": parsed.stem_text[:80],
                }
            )
        payload.append(
            {
                "section_name": section.title,
                "section_type": section.section_type,
                "question_count": len(section.blocks),
                "samples": items,
            }
        )

    print(
        json.dumps(
            {"sample_path": str(sample_path), "sections": payload},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
