from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .context import ContentType, GenerationContext
from .review import ReviewReport


class Citation(BaseModel):
    source_label: str
    chunk_id: str | None = None
    file_id: str | None = None
    page: int | None = None
    snippet: str


class Claim(BaseModel):
    text: str
    citations: list[Citation] = Field(default_factory=list)


class XiaohongshuPublishPackage(BaseModel):
    title_options: list[str] = Field(default_factory=list)
    body: str = ""
    cover_text: str = ""
    carousel_pages: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    comment_guides: list[str] = Field(default_factory=list)


class GenerationResult(BaseModel):
    content_type: str
    title: str
    sections: list[dict] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    raw_markdown: str
    publish_package: XiaohongshuPublishPackage | None = None
    unverified: bool = False


class GenerationRequest(BaseModel):
    mode: Literal["ragflow", "direct"]
    subject: str
    category: str | None = None
    chapter: str | None = None
    content_type: ContentType
    options: dict = Field(default_factory=dict)
    user_notes: str | None = None
    library_file_ids: list[str] = Field(default_factory=list)
    ragflow_dataset_ids: list[str] = Field(default_factory=list)


class GenerationJob(BaseModel):
    id: str
    context: GenerationContext
    status: Literal[
        "pending",
        "retrieving",
        "generating",
        "reviewing",
        "done",
        "failed",
    ]
    result: GenerationResult | None = None
    review: ReviewReport | None = None
    created_at: datetime
    error: str | None = None
