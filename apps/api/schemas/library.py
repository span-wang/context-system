from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SourceType = Literal["textbook", "standard", "regulation", "exam", "note", "other"]
SourceAuthority = Literal["high", "medium", "low"]
LibraryParseMode = Literal["preview", "reparse"]
ParseOutputFormat = Literal["markdown", "text"]


class FileMetadata(BaseModel):
    subject: str
    category: str | None = None
    chapter: str | None = None
    source_type: SourceType = "other"
    source_authority: SourceAuthority = "medium"
    source_title: str = ""
    source_publisher: str | None = None
    source_code: str | None = None
    source_version: str | None = None
    year: int | None = None
    tags: list[str] = Field(default_factory=list)


class LibraryFile(BaseModel):
    id: str
    sha256: str
    filename: str
    size: int
    mime: str
    storage_path: str
    subject: str
    category: str | None = None
    chapter: str | None = None
    source_type: SourceType = "other"
    source_authority: SourceAuthority = "medium"
    source_title: str
    source_publisher: str | None = None
    source_code: str | None = None
    source_version: str | None = None
    year: int | None = None
    tags: list[str] = Field(default_factory=list)
    token_count: int | None = None
    created_at: datetime
    last_used_at: datetime | None = None


class LibraryFilePreview(BaseModel):
    file_id: str
    filename: str
    token_count: int
    provider: str = "unknown"
    text: str
    markdown: str
    content: str
    output_format: ParseOutputFormat = "markdown"
    table_count: int = 0
    warning_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    truncated: bool
    parse_options: dict[str, object] = Field(default_factory=dict)


class LibraryParseResultSummary(BaseModel):
    id: str
    file_id: str
    sequence_number: int
    provider: str
    token_count: int
    created_at: datetime


class LibraryReparseResponse(LibraryFilePreview):
    stored_result_id: str
    stored_sequence_number: int
    kept_results: list[LibraryParseResultSummary] = Field(default_factory=list)


class LibraryParseJobResponse(BaseModel):
    job_id: int
    file_id: str
    mode: LibraryParseMode
    status: str
    progress: int


class LibraryParseJobStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_type: str
    scope_type: str
    scope_config_json: dict | None = None
    status: str
    progress: int
    result_summary_json: dict | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class LibraryFilePatch(BaseModel):
    filename: str | None = None
    subject: str | None = None
    category: str | None = None
    chapter: str | None = None
    source_type: SourceType | None = None
    source_authority: SourceAuthority | None = None
    source_title: str | None = None
    source_publisher: str | None = None
    source_code: str | None = None
    source_version: str | None = None
    year: int | None = None
    tags: list[str] | None = None
