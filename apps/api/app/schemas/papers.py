from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import ORMModel

PaperParseExecutionMode = Literal["ocr_only", "ai_cleanup_split", "full_chain"]


class PaperParseResponse(ORMModel):
    paper_id: int
    asset_id: int
    parse_status: str
    paper_status: str
    question_count: int
    section_count: int
    tagged_count: int
    preview: str | None = None
    provider: str | None = None
    output_format: Literal["markdown", "text"] = "markdown"
    warnings: list[str] = Field(default_factory=list)
    parse_options: dict[str, object] = Field(default_factory=dict)
    parse_runtime: dict[str, object] = Field(default_factory=dict)
    execution_mode: PaperParseExecutionMode = "full_chain"
    token_count: int | None = None
    dataset_sample_path: str | None = None
    dataset_auto_exported: bool = False
    dataset_export_error: str | None = None
    ai_standardize_job_count: int = 0
    ai_standardize_requested_count: int = 0
    ai_standardize_job_ids: list[int] = Field(default_factory=list)


class PaperParseJobResponse(ORMModel):
    job_id: int
    paper_id: int
    status: str
    progress: int
    execution_mode: PaperParseExecutionMode = "full_chain"


class AnalysisJobResponse(ORMModel):
    id: int
    job_type: str
    subject_id: int | None = None
    scope_type: str
    scope_config_json: dict | None = None
    status: str
    progress: int
    result_summary_json: dict | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class PaperUploadResponse(ORMModel):
    id: int
    asset_id: int
    paper_name: str
    filename: str
    sha256: str
    status: str
    review_status: str
    asset_parse_status: str


class PaperDeleteResponse(ORMModel):
    id: int
    paper_name: str
    deleted: bool
    removed_asset: bool = False
    removed_storage_file: bool = False
    removed_dataset_dir: bool = False
    removed_parsed_cache_files: int = 0
    removed_pdf_checkpoint_dirs: int = 0
    cleanup_warnings: list[str] = Field(default_factory=list)


class PaperSummary(ORMModel):
    id: int
    subject_id: int | None = None
    paper_name: str
    paper_code: str | None = None
    category: str | None = None
    category_id: int | None = None
    exam_year: int | None = None
    exam_month: int | None = None
    exam_region: str | None = None
    exam_type: str | None = None
    paper_type: str | None = None
    status: str
    review_status: str
    total_question_count: int
    total_score: int | None = None


class PaperSectionResponse(ORMModel):
    id: int
    section_name: str
    question_type: str
    start_no: int | None = None
    end_no: int | None = None
    score: int | None = None
    sort_order: int


class PaperDetailResponse(PaperSummary):
    asset_id: int | None = None
    subject_name: str | None = None
    asset_filename: str | None = None
    asset_parse_status: str | None = None
    active_parse_job_id: int | None = None
    active_parse_job_status: str | None = None
    active_parse_stage: str | None = None
    active_parse_progress: int | None = None
    sections: list[PaperSectionResponse]
