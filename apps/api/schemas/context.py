from typing import Literal

from pydantic import BaseModel, Field


ContentType = Literal[
    "mnemonic",
    "tri_color",
    "summary_pages",
    "formula_dict",
    "compare_table",
    "exam_review",
]


class ContextSource(BaseModel):
    text: str
    source_label: str
    source_type: str = "other"
    authority: Literal["high", "medium", "low", "unknown"] = "unknown"
    chunk_id: str | None = None
    file_id: str | None = None
    page: int | None = None


class GenerationContext(BaseModel):
    mode: Literal["ragflow", "direct"]
    subject: str
    category: str | None = None
    chapter: str | None = None
    content_type: ContentType
    options: dict = Field(default_factory=dict)
    sources: list[ContextSource] = Field(default_factory=list)
    user_notes: str | None = None
    has_authoritative_source: bool = False

