from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


SourceType = Literal["textbook", "standard", "regulation", "exam", "note", "other"]
SourceAuthority = Literal["high", "medium", "low"]


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
    parsed_text: str | None = None
    token_count: int | None = None
    created_at: datetime
    last_used_at: datetime | None = None


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

