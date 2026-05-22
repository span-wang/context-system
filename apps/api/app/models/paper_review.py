from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ManagedEntityMixin


LARGE_TEXT = Text().with_variant(mysql.LONGTEXT(), "mysql")


class PaperReviewQuestion(Base, ManagedEntityMixin):
    __tablename__ = "paper_review_questions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("exam_papers.id", ondelete="CASCADE"), index=True)
    section_id: Mapped[int | None] = mapped_column(ForeignKey("paper_sections.id", ondelete="CASCADE"), nullable=True, index=True)
    parent_question_id: Mapped[int | None] = mapped_column(
        ForeignKey("paper_review_questions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    question_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    content_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    question_no: Mapped[str] = mapped_column(String(32))
    node_role: Mapped[str] = mapped_column(String(32), default="standalone")
    question_type: Mapped[str] = mapped_column(String(64))
    source_section_name: Mapped[str] = mapped_column(String(128))
    source_raw_text: Mapped[str] = mapped_column(LARGE_TEXT)
    group_stem: Mapped[str | None] = mapped_column(LARGE_TEXT, nullable=True)
    material_text: Mapped[str | None] = mapped_column(LARGE_TEXT, nullable=True)
    stem_text: Mapped[str] = mapped_column(LARGE_TEXT)
    options_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    answer_text: Mapped[str | None] = mapped_column(LARGE_TEXT, nullable=True)
    analysis_text: Mapped[str | None] = mapped_column(LARGE_TEXT, nullable=True)
    difficulty_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    subquestion_count: Mapped[int] = mapped_column(Integer, default=0)
    quality_issues_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    parse_status: Mapped[str] = mapped_column(String(32), default="parsed")
    review_status: Mapped[str] = mapped_column(String(32), default="pending")
    review_note: Mapped[str | None] = mapped_column(LARGE_TEXT, nullable=True)
    ai_review_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ai_review_note: Mapped[str | None] = mapped_column(LARGE_TEXT, nullable=True)
    ai_standardization_note: Mapped[str | None] = mapped_column(LARGE_TEXT, nullable=True)
    last_ai_standardized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ai_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaperReviewQuestionKnowledgePoint(Base, ManagedEntityMixin):
    __tablename__ = "paper_review_question_knowledge_points"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("paper_review_questions.id", ondelete="CASCADE"), index=True)
    knowledge_point_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="suggested")
    relation_type: Mapped[str] = mapped_column(String(32), default="secondary")
    source: Mapped[str] = mapped_column(String(32), default="rule")
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    reason: Mapped[str | None] = mapped_column(LARGE_TEXT, nullable=True)
    rank: Mapped[int] = mapped_column(Integer, default=0)
