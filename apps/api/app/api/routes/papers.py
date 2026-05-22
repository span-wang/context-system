from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.papers import (
    AnalysisJobResponse,
    PaperDeleteResponse,
    PaperParseJobResponse,
    PaperParseExecutionMode,
    PaperDetailResponse,
    PaperParseResponse,
    PaperSummary,
    PaperUploadResponse,
)
from app.services.audit import AuditService
from app.services.paper_parse_jobs import start_paper_parse_job
from app.services.papers import PaperService
from library.parse_options import (
    DEFAULT_PARSE_OUTPUT_FORMAT,
    DEFAULT_PARSE_PRESET,
    ParseOutputFormat,
    ParsePreset,
    build_document_parse_options,
)


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
        None,
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
    preset: ParsePreset = Form(DEFAULT_PARSE_PRESET),
    output_format: ParseOutputFormat = Form(DEFAULT_PARSE_OUTPUT_FORMAT),
    execution_mode: PaperParseExecutionMode = Form("full_chain"),
    raw_ocr_mode: bool | None = Form(None),
    preserve_pdf_image_content: bool | None = Form(None),
    force_ocr: bool | None = Form(None),
    render_dpi: int | None = Form(None),
    crop_header_ratio: float | None = Form(None),
    crop_footer_ratio: float | None = Form(None),
    trim_margins: bool | None = Form(None),
    remove_repeated_lines: bool | None = Form(None),
    watermark_detection: bool | None = Form(None),
    enable_formula_recognition: bool | None = Form(None),
    pdf_page_chunk_size: int | None = Form(None, ge=1, le=50),
    session: Session = Depends(get_session),
) -> PaperParseResponse:
    options = build_document_parse_options(
        preset=preset,
        output_format=output_format,
        raw_ocr_mode=raw_ocr_mode,
        preserve_pdf_image_content=preserve_pdf_image_content,
        force_ocr=force_ocr,
        render_dpi=render_dpi,
        crop_header_ratio=crop_header_ratio,
        crop_footer_ratio=crop_footer_ratio,
        trim_margins=trim_margins,
        remove_repeated_lines=remove_repeated_lines,
        watermark_detection=watermark_detection,
        enable_formula_recognition=enable_formula_recognition,
        pdf_page_chunk_size=pdf_page_chunk_size,
    )
    result = PaperService(session).parse_paper(paper_id, options=options, execution_mode=execution_mode)
    AuditService(session).log(
        None,
        module="papers",
        action="parse",
        target_type="paper",
        target_id=paper_id,
        payload={
            "execution_mode": execution_mode,
            "question_count": result.question_count,
            "tagged_count": result.tagged_count,
            "parse_options": result.parse_options,
            "provider": result.provider,
            "parse_runtime": result.parse_runtime,
        },
    )
    return result


@router.get("/{paper_id}/preview")
def preview_paper(
    paper_id: int,
    preset: ParsePreset = Query(DEFAULT_PARSE_PRESET),
    output_format: ParseOutputFormat = Query(DEFAULT_PARSE_OUTPUT_FORMAT),
    raw_ocr_mode: bool | None = Query(None),
    preserve_pdf_image_content: bool | None = Query(None),
    force_ocr: bool | None = Query(None),
    render_dpi: int | None = Query(None, ge=96, le=360),
    crop_header_ratio: float | None = Query(None, ge=0.0, le=0.2),
    crop_footer_ratio: float | None = Query(None, ge=0.0, le=0.2),
    trim_margins: bool | None = Query(None),
    remove_repeated_lines: bool | None = Query(None),
    watermark_detection: bool | None = Query(None),
    enable_formula_recognition: bool | None = Query(None),
    pdf_page_chunk_size: int | None = Query(None, ge=1, le=50),
    session: Session = Depends(get_session),
):
    options = build_document_parse_options(
        preset=preset,
        output_format=output_format,
        raw_ocr_mode=raw_ocr_mode,
        preserve_pdf_image_content=preserve_pdf_image_content,
        force_ocr=force_ocr,
        render_dpi=render_dpi,
        crop_header_ratio=crop_header_ratio,
        crop_footer_ratio=crop_footer_ratio,
        trim_margins=trim_margins,
        remove_repeated_lines=remove_repeated_lines,
        watermark_detection=watermark_detection,
        enable_formula_recognition=enable_formula_recognition,
        pdf_page_chunk_size=pdf_page_chunk_size,
    )
    return PaperService(session).preview_paper(paper_id, options=options)


@router.post("/{paper_id}/parse-jobs", response_model=PaperParseJobResponse)
def start_parse_paper_job(
    paper_id: int,
    preset: ParsePreset = Form(DEFAULT_PARSE_PRESET),
    output_format: ParseOutputFormat = Form(DEFAULT_PARSE_OUTPUT_FORMAT),
    execution_mode: PaperParseExecutionMode = Form("full_chain"),
    raw_ocr_mode: bool | None = Form(None),
    preserve_pdf_image_content: bool | None = Form(None),
    force_ocr: bool | None = Form(None),
    render_dpi: int | None = Form(None),
    crop_header_ratio: float | None = Form(None),
    crop_footer_ratio: float | None = Form(None),
    trim_margins: bool | None = Form(None),
    remove_repeated_lines: bool | None = Form(None),
    watermark_detection: bool | None = Form(None),
    enable_formula_recognition: bool | None = Form(None),
    pdf_page_chunk_size: int | None = Form(None, ge=1, le=50),
    session: Session = Depends(get_session),
) -> PaperParseJobResponse:
    options = build_document_parse_options(
        preset=preset,
        output_format=output_format,
        raw_ocr_mode=raw_ocr_mode,
        preserve_pdf_image_content=preserve_pdf_image_content,
        force_ocr=force_ocr,
        render_dpi=render_dpi,
        crop_header_ratio=crop_header_ratio,
        crop_footer_ratio=crop_footer_ratio,
        trim_margins=trim_margins,
        remove_repeated_lines=remove_repeated_lines,
        watermark_detection=watermark_detection,
        enable_formula_recognition=enable_formula_recognition,
        pdf_page_chunk_size=pdf_page_chunk_size,
    )
    job = start_paper_parse_job(session, paper_id, options, execution_mode=execution_mode)
    job_id = job.id
    job_status = job.status
    job_progress = job.progress
    AuditService(session).log(
        None,
        module="papers",
        action="parse_job_start",
        target_type="paper",
        target_id=paper_id,
        payload={"job_id": job_id, "execution_mode": execution_mode, "parse_options": options.normalized_dump()},
    )
    return PaperParseJobResponse(
        job_id=job_id,
        paper_id=paper_id,
        status=job_status,
        progress=job_progress,
        execution_mode=execution_mode,
    )


@router.get("/parse-jobs/{job_id}", response_model=AnalysisJobResponse)
def get_parse_paper_job(job_id: int, session: Session = Depends(get_session)) -> AnalysisJobResponse:
    job = PaperService(session).repository.get_job(job_id)
    if job is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="任务不存在")
    return AnalysisJobResponse.model_validate(job)


@router.get("/{paper_id}", response_model=PaperDetailResponse)
def get_paper(paper_id: int, session: Session = Depends(get_session)) -> PaperDetailResponse:
    return PaperService(session).get_paper(paper_id)


@router.delete("/{paper_id}", response_model=PaperDeleteResponse)
def delete_paper(
    paper_id: int,
    session: Session = Depends(get_session),
) -> PaperDeleteResponse:
    result = PaperService(session).delete_paper(paper_id)
    AuditService(session).log(
        None,
        module="papers",
        action="delete",
        target_type="paper",
        target_id=paper_id,
        payload={
            "paper_name": result.paper_name,
            "removed_asset": result.removed_asset,
            "removed_storage_file": result.removed_storage_file,
            "removed_dataset_dir": result.removed_dataset_dir,
            "removed_parsed_cache_files": result.removed_parsed_cache_files,
            "removed_pdf_checkpoint_dirs": result.removed_pdf_checkpoint_dirs,
            "cleanup_warnings": result.cleanup_warnings,
        },
    )
    return result
