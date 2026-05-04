from hashlib import sha1
from typing import Literal

from pydantic import BaseModel, Field, model_validator


ReviewMode = Literal["llm_only", "document_only", "hybrid"]
ReviewItemStatus = Literal["pending", "confirmed", "replaced", "skipped"]


def make_review_item_id(issue: str, suggestion: str | None = None, index: int = 0) -> str:
    raw = "|".join([issue.strip(), (suggestion or "").strip(), str(index)])
    digest = sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"ri_{index + 1}_{digest}"


class ReviewRequest(BaseModel):
    mode: ReviewMode = "hybrid"


class ReviewItem(BaseModel):
    id: str
    issue: str
    suggestion: str | None = None
    original_text: str | None = None
    replacement_text: str | None = None
    status: ReviewItemStatus = "pending"
    replace_count: int = 0


class ReviewItemUpdateRequest(BaseModel):
    status: ReviewItemStatus | None = None
    original_text: str | None = None
    replacement_text: str | None = None


class ReviewItemReplaceRequest(BaseModel):
    original_text: str | None = None
    replacement_text: str | None = None
    replace_all: bool = False


class ReviewReport(BaseModel):
    pass_overall: bool
    strict_mode: bool
    mode: ReviewMode = "hybrid"
    evidence_policy: str = "model_and_documents"
    llm_used: bool = False
    evidence_source_count: int = 0
    citation_check: dict = Field(default_factory=dict)
    nli_results: list[dict] = Field(default_factory=list)
    version_conflicts: list[dict] = Field(default_factory=list)
    numeric_checks: list[dict] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    items: list[ReviewItem] = Field(default_factory=list)
    unverified_warning: str | None = None

    @model_validator(mode="after")
    def ensure_items(self) -> "ReviewReport":
        if self.items or not self.issues:
            return self
        self.items = [
            ReviewItem(
                id=make_review_item_id(issue, self.suggestions[index] if index < len(self.suggestions) else None, index),
                issue=issue,
                suggestion=self.suggestions[index] if index < len(self.suggestions) else None,
            )
            for index, issue in enumerate(self.issues)
        ]
        return self
