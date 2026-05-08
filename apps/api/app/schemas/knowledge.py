from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class SubjectUpsertRequest(BaseModel):
    code: str
    name: str
    status: str = "active"


class SubjectResponse(ORMModel):
    id: int
    code: str
    name: str
    status: str


class SubjectDeleteResponse(BaseModel):
    id: int
    name: str
    deleted: bool


class BatchDeleteRequest(BaseModel):
    ids: list[int] = Field(min_length=1)


class SubjectDeleteSkippedItem(BaseModel):
    id: int
    name: str | None = None
    reason: str


class SubjectBatchDeleteResponse(BaseModel):
    requested_count: int
    deleted_count: int
    skipped_count: int
    deleted: list[SubjectDeleteResponse]
    skipped: list[SubjectDeleteSkippedItem]
    message: str


class SubjectCategoryUpsertRequest(BaseModel):
    subject_id: int
    name: str
    sort_order: int = 0


class SubjectCategoryResponse(ORMModel):
    id: int
    subject_id: int
    name: str
    sort_order: int


class ChapterUpsertRequest(BaseModel):
    subject_id: int
    category_id: int | None = None
    parent_id: int | None = None
    name: str
    level: int | None = None
    path: str | None = None
    sort_order: int = 0


class ChapterResponse(ORMModel):
    id: int
    subject_id: int
    category_id: int | None = None
    parent_id: int | None = None
    name: str
    level: int
    path: str
    sort_order: int


class ChapterDeleteResponse(BaseModel):
    id: int
    name: str
    deleted: bool
    removed_chapter_count: int
    unbound_point_count: int


class ChapterBatchDeleteResponse(BaseModel):
    requested_count: int
    removed_chapter_count: int
    unbound_point_count: int
    missing_count: int
    message: str


class ChapterMarkdownImportRequest(BaseModel):
    subject_id: int
    category_id: int
    markdown: str = Field(min_length=1)


class ChapterMarkdownImportResponse(BaseModel):
    subject_id: int
    chapter_created: int
    chapter_skipped: int
    chapters: list[ChapterResponse]
    message: str


class KnowledgePointUpsertRequest(BaseModel):
    subject_id: int
    category_id: int | None = None
    chapter_id: int | None = None
    parent_id: int | None = None
    name: str
    level: int | None = None
    path: str | None = None
    description: str | None = None
    keywords_json: list[str] = Field(default_factory=list)
    status: str = "active"
    sort_order: int = 0


class KnowledgePointResponse(ORMModel):
    id: int
    subject_id: int
    category_id: int | None = None
    chapter_id: int | None = None
    parent_id: int | None = None
    name: str
    level: int
    path: str
    description: str | None = None
    keywords_json: list[str] | None = None
    status: str
    sort_order: int


class KnowledgePointMarkdownImportRequest(BaseModel):
    subject_id: int
    category_id: int | None = None
    markdown: str = Field(min_length=1)
    import_mode: Literal["point", "detail"] = "point"


class KnowledgePointMarkdownImportResponse(BaseModel):
    subject_id: int
    point_created: int
    point_skipped: int
    points: list[KnowledgePointResponse]
    message: str


class TextbookUpsertRequest(BaseModel):
    subject_id: int
    category_id: int | None = None
    source_title: str
    filename: str | None = None
    year: int | None = None
    region: str | None = None
    source_version: str | None = None
    tags_json: list[str] = Field(default_factory=list)
    parse_status: str = "metadata"
    token_count: int | None = None


class TextbookResponse(ORMModel):
    id: int
    subject_id: int | None = None
    category_id: int | None = None
    source_title: str
    filename: str
    year: int | None = None
    region: str | None = None
    source_version: str | None = None
    tags_json: list[str] | None = None
    parse_status: str
    ocr_status: str
    token_count: int | None = None
    file_size: int


class TextbookAutoBuildRequest(BaseModel):
    max_chapters: int = Field(default=12, ge=1, le=30)
    knowledge_points_per_chapter: int = Field(default=4, ge=1, le=8)


class TextbookAutoBuildResponse(BaseModel):
    textbook_id: int
    subject_id: int
    source: str
    chapter_created: int
    chapter_skipped: int
    point_created: int
    point_skipped: int
    review_task_created: int
    chapters: list[ChapterResponse]
    points: list[KnowledgePointResponse]
    message: str
