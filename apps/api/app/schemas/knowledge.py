from __future__ import annotations

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
    parent_id: int | None = None
    name: str
    level: int | None = None
    path: str | None = None
    sort_order: int = 0


class ChapterResponse(ORMModel):
    id: int
    subject_id: int
    parent_id: int | None = None
    name: str
    level: int
    path: str
    sort_order: int


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
