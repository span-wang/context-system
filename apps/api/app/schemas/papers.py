from __future__ import annotations

from pydantic import Field

from app.schemas.common import ORMModel


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
    warnings: list[str] = Field(default_factory=list)
    parse_options: dict[str, object] = Field(default_factory=dict)


class PaperParseJobResponse(ORMModel):
    job_id: int
    paper_id: int
    status: str
    progress: int


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
    removed_question_count: int
    removed_source_link_count: int


class PaperSummary(ORMModel):
    id: int
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
    subject_name: str | None = None
    asset_filename: str | None = None
    asset_parse_status: str | None = None
    sections: list[PaperSectionResponse]
