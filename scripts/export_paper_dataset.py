from __future__ import annotations

import argparse
import json
from pathlib import Path

from paper_dataset_common import (
    bootstrap_api_path,
    get_repo_root,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export paper parser dataset samples from the current project database.",
    )
    parser.add_argument(
        "--paper-id",
        dest="paper_ids",
        action="append",
        type=int,
        help="Export one or more specific paper IDs. Repeat the flag to export multiple papers.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of papers to export when --paper-id is not provided.",
    )
    parser.add_argument(
        "--needs-review-only",
        action="store_true",
        help="Only export papers that already contain needs_review questions.",
    )
    parser.add_argument(
        "--include-source",
        action="store_true",
        help="Copy the original uploaded asset into each sample folder when the file still exists.",
    )
    parser.add_argument(
        "--init-gold",
        action="store_true",
        help="Initialize gold.json from the current prediction when gold.json does not exist yet.",
    )
    parser.add_argument(
        "--overwrite-gold",
        action="store_true",
        help="Overwrite an existing gold.json when used together with --init-gold.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(get_repo_root() / "data" / "paper_parser_dataset"),
        help="Directory used to write exported dataset samples.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bootstrap_api_path()

    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.asset import Asset, ExamPaper, PaperSection
    from app.models.question import ExamQuestion
    from app.models.subject import Subject, SubjectCategory
    from app.services.paper_dataset import export_paper_parser_sample

    output_root = Path(args.output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    exported_count = 0
    skipped_count = 0
    session = SessionLocal()
    try:
        stmt = (
            select(ExamPaper, Asset, Subject, SubjectCategory)
            .join(Asset, ExamPaper.asset_id == Asset.id, isouter=True)
            .join(Subject, ExamPaper.subject_id == Subject.id, isouter=True)
            .join(SubjectCategory, ExamPaper.category_id == SubjectCategory.id, isouter=True)
            .order_by(ExamPaper.id.desc())
        )
        if args.paper_ids:
            stmt = stmt.where(ExamPaper.id.in_(args.paper_ids))

        rows = list(session.execute(stmt))
        for row in rows:
            paper, asset, subject, category = row
            questions = list(
                session.scalars(
                    select(ExamQuestion).where(ExamQuestion.paper_id == paper.id).order_by(ExamQuestion.id.asc())
                )
            )
            sections = list(
                session.scalars(
                    select(PaperSection).where(PaperSection.paper_id == paper.id).order_by(PaperSection.sort_order.asc())
                )
            )

            needs_review_count = sum(1 for question in questions if question.parse_status == "needs_review")
            if args.needs_review_only and needs_review_count <= 0:
                continue

            source_text = ((asset.parsed_text if asset else None) or "").strip()
            if not source_text:
                skipped_count += 1
                print(f"[skip] paper_id={paper.id} has no asset.parsed_text to export.")
                continue

            sample_dir = export_paper_parser_sample(
                paper_id=paper.id,
                paper_name=paper.paper_name,
                source_text=source_text,
                paper_status=paper.status,
                paper_review_status=paper.review_status,
                exam_year=paper.exam_year,
                exam_month=paper.exam_month,
                exam_region=paper.exam_region,
                paper_type=paper.paper_type,
                subject_name=subject.name if subject else None,
                subject_code=subject.code if subject else None,
                category_name=category.name if category else None,
                asset_id=asset.id if asset else None,
                asset_filename=asset.filename if asset else None,
                asset_mime_type=asset.mime_type if asset else None,
                asset_storage_path=asset.storage_path if asset else None,
                asset_parse_status=asset.parse_status if asset else None,
                asset_ocr_status=asset.ocr_status if asset else None,
                stored_section_count=len(sections),
                stored_question_count=len(questions),
                stored_needs_review_count=needs_review_count,
                output_root=output_root,
                init_gold=args.init_gold,
                include_source=args.include_source,
            )
            if args.init_gold and args.overwrite_gold:
                gold_template_path = sample_dir / "gold.template.json"
                gold_path = sample_dir / "gold.json"
                if gold_template_path.exists():
                    gold_path.write_text(gold_template_path.read_text(encoding="utf-8"), encoding="utf-8")

            exported_count += 1
            meta = json.loads((sample_dir / "meta.json").read_text(encoding="utf-8"))
            print(f"[ok] paper_id={paper.id} sample={sample_dir.name} "
                  f"predicted_sections={meta['predicted_section_count']} predicted_questions={meta['predicted_question_count']}")
            if not args.paper_ids and exported_count >= args.limit:
                break
    finally:
        session.close()

    print(f"exported={exported_count} skipped={skipped_count} output_dir={output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
