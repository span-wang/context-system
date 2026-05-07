from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_session, require_roles
from app.schemas.auth import CurrentUserResponse
from app.schemas.papers import (
    PaperDeleteResponse,
    PaperParseJobResponse,
    PaperDetailResponse,
    PaperParseResponse,
    PaperSummary,
    PaperUploadResponse,
)
from app.services.audit import AuditService
from app.services.paper_parse_jobs import start_paper_parse_job
from app.services.papers import PaperService
from library.parse_options import DocumentParseOptions, ParsePreset


router = APIRouter(prefix="/api/papers", tags=["papers"])


@router.get("", response_model=list[PaperSummary])
def list_papers(session: Session = Depends(get_session)) -> list[PaperSummary]:
    return PaperService(session).list_papers()


@router.post("/upload", response_model=PaperUploadResponse)
async def upload_paper(
    file: UploadFile = File(...),
    paper_name: str = Form(...),
    subject_id: int | None = Form(None),
    subject_code: str | None = Form(None),
    subject_name: str | None = Form(None),
    category: str | None = Form(None),
    exam_year: int | None = Form(None),
    exam_month: int | None = Form(None),
    exam_region: str | None = Form(None),
    exam_type: str | None = Form(None),
    paper_type: str | None = Form(None),
    paper_code: str | None = Form(None),
    session: Session = Depends(get_session),
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "operator")),
) -> PaperUploadResponse:
    result = await PaperService(session).upload_paper(
        file=file,
        paper_name=paper_name,
        subject_id=subject_id,
        subject_code=subject_code,
        subject_name=subject_name,
        category=category,
        exam_year=exam_year,
        exam_month=exam_month,
        exam_region=exam_region,
        exam_type=exam_type,
        paper_type=paper_type,
        paper_code=paper_code,
    )
    AuditService(session).log(
        current_user,
        module="papers",
        action="upload",
        target_type="paper",
        target_id=result.id,
        payload={"paper_name": paper_name, "filename": file.filename, "subject": subject_name, "category": category},
    )
    return result


@router.post("/{paper_id}/parse", response_model=PaperParseResponse)
def parse_paper(
    paper_id: int,
    preset: ParsePreset = Form("auto"),
    force_ocr: bool | None = Form(None),
    render_dpi: int | None = Form(None),
    crop_header_ratio: float | None = Form(None),
    crop_footer_ratio: float | None = Form(None),
    trim_margins: bool | None = Form(None),
    remove_repeated_lines: bool | None = Form(None),
    watermark_detection: bool | None = Form(None),
    enable_formula_recognition: bool | None = Form(None),
    session: Session = Depends(get_session),
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "reviewer")),
) -> PaperParseResponse:
    options = DocumentParseOptions(
        preset=preset,
        force_ocr=force_ocr,
        render_dpi=render_dpi,
        crop_header_ratio=crop_header_ratio,
        crop_footer_ratio=crop_footer_ratio,
        trim_margins=trim_margins,
        remove_repeated_lines=remove_repeated_lines,
        watermark_detection=watermark_detection,
        enable_formula_recognition=enable_formula_recognition,
    )
    result = PaperService(session).parse_paper(paper_id, options=options)
    AuditService(session).log(
        current_user,
        module="papers",
        action="parse",
        target_type="paper",
        target_id=paper_id,
        payload={
            "question_count": result.question_count,
            "tagged_count": result.tagged_count,
            "parse_options": result.parse_options,
            "provider": result.provider,
        },
    )
    return result


@router.post("/{paper_id}/parse-jobs", response_model=PaperParseJobResponse)
def start_parse_paper_job(
    paper_id: int,
    preset: ParsePreset = Form("auto"),
    force_ocr: bool | None = Form(None),
    render_dpi: int | None = Form(None),
    crop_header_ratio: float | None = Form(None),
    crop_footer_ratio: float | None = Form(None),
    trim_margins: bool | None = Form(None),
    remove_repeated_lines: bool | None = Form(None),
    watermark_detection: bool | None = Form(None),
    enable_formula_recognition: bool | None = Form(None),
    session: Session = Depends(get_session),
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "reviewer")),
) -> PaperParseJobResponse:
    options = DocumentParseOptions(
        preset=preset,
        force_ocr=force_ocr,
        render_dpi=render_dpi,
        crop_header_ratio=crop_header_ratio,
        crop_footer_ratio=crop_footer_ratio,
        trim_margins=trim_margins,
        remove_repeated_lines=remove_repeated_lines,
        watermark_detection=watermark_detection,
        enable_formula_recognition=enable_formula_recognition,
    )
    job = start_paper_parse_job(session, paper_id, options)
    job_id = job.id
    job_status = job.status
    job_progress = job.progress
    AuditService(session).log(
        current_user,
        module="papers",
        action="parse_job_start",
        target_type="paper",
        target_id=paper_id,
        payload={"job_id": job_id, "parse_options": options.normalized_dump()},
    )
    return PaperParseJobResponse(job_id=job_id, paper_id=paper_id, status=job_status, progress=job_progress)


@router.get("/{paper_id}", response_model=PaperDetailResponse)
def get_paper(paper_id: int, session: Session = Depends(get_session)) -> PaperDetailResponse:
    return PaperService(session).get_paper(paper_id)


@router.delete("/{paper_id}", response_model=PaperDeleteResponse)
def delete_paper(
    paper_id: int,
    session: Session = Depends(get_session),
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "operator")),
) -> PaperDeleteResponse:
    result = PaperService(session).delete_paper(paper_id)
    AuditService(session).log(
        current_user,
        module="papers",
        action="delete",
        target_type="paper",
        target_id=paper_id,
        payload={
            "paper_name": result.paper_name,
            "removed_question_count": result.removed_question_count,
            "removed_source_link_count": result.removed_source_link_count,
        },
    )
    return result
