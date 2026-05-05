from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .context import ContentType


TopicStatus = Literal[
    "idea",
    "planned",
    "drafting",
    "generated",
    "reviewing",
    "needs_changes",
    "awaiting_confirm",
    "approved",
    "exported",
    "published",
    "archived",
]
ReviewStatus = Literal["not_started", "reviewing", "passed", "needs_changes", "waived"]
TopicPriority = Literal["low", "medium", "high", "urgent"]


class WorkflowTopicBase(BaseModel):
    title: str
    brief: str | None = None
    subject: str
    category: str | None = None
    chapter: str | None = None
    content_type: ContentType = "tri_color"
    owner: str | None = None
    status: TopicStatus = "idea"
    review_status: ReviewStatus = "not_started"
    priority: TopicPriority = "medium"
    scheduled_date: date | None = None
    due_date: date | None = None
    publish_channel: str = "xiaohongshu"
    content_goal: str | None = None
    audience: str | None = None
    material_file_ids: list[str] = Field(default_factory=list)
    ragflow_dataset_ids: list[str] = Field(default_factory=list)
    generation_job_id: str | None = None
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    published_at: datetime | None = None


class WorkflowTopic(WorkflowTopicBase):
    id: str
    created_at: datetime
    updated_at: datetime


class WorkflowTopicCreate(BaseModel):
    title: str
    brief: str | None = None
    subject: str
    category: str | None = None
    chapter: str | None = None
    content_type: ContentType = "tri_color"
    owner: str | None = None
    status: TopicStatus = "idea"
    review_status: ReviewStatus = "not_started"
    priority: TopicPriority = "medium"
    scheduled_date: date | None = None
    due_date: date | None = None
    publish_channel: str = "xiaohongshu"
    content_goal: str | None = None
    audience: str | None = None
    material_file_ids: list[str] = Field(default_factory=list)
    ragflow_dataset_ids: list[str] = Field(default_factory=list)


class WorkflowTopicPatch(BaseModel):
    title: str | None = None
    brief: str | None = None
    subject: str | None = None
    category: str | None = None
    chapter: str | None = None
    content_type: ContentType | None = None
    owner: str | None = None
    status: TopicStatus | None = None
    review_status: ReviewStatus | None = None
    priority: TopicPriority | None = None
    scheduled_date: date | None = None
    due_date: date | None = None
    publish_channel: str | None = None
    content_goal: str | None = None
    audience: str | None = None
    material_file_ids: list[str] | None = None
    ragflow_dataset_ids: list[str] | None = None
    generation_job_id: str | None = None
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    published_at: datetime | None = None
    note: str | None = None
    actor: str | None = None


class WorkflowGenerateRequest(BaseModel):
    mode: Literal["direct", "ragflow"] = "direct"
    pages: int = 10
    options: dict[str, Any] = Field(default_factory=dict)
    user_notes: str | None = None


class WorkflowGenerateResponse(BaseModel):
    topic: WorkflowTopic
    job_id: str


class WorkflowConfirmRequest(BaseModel):
    confirmed_by: str | None = None
    note: str | None = None


class WorkflowExportRequest(BaseModel):
    mark_exported: bool = True
    actor: str | None = None
    note: str | None = None


class WorkflowEvent(BaseModel):
    id: str
    topic_id: str
    version: int
    event_type: str
    note: str | None = None
    actor: str | None = None
    snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
