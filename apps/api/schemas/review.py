from typing import Literal

from pydantic import BaseModel, Field


ReviewMode = Literal["llm_only", "document_only", "hybrid"]


class ReviewRequest(BaseModel):
    mode: ReviewMode = "hybrid"


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
    unverified_warning: str | None = None
