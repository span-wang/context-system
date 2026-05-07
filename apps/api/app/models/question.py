from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ManagedEntityMixin


class ExamQuestion(Base, ManagedEntityMixin):
    __tablename__ = "exam_questions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("exam_papers.id"), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), index=True)
    section_id: Mapped[int | None] = mapped_column(ForeignKey("paper_sections.id"), nullable=True, index=True)
    question_no: Mapped[str] = mapped_column(String(32))
    question_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    question_type: Mapped[str] = mapped_column(String(64))
    stem_text: Mapped[str] = mapped_column(Text)
    options_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_page_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_page_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    difficulty_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    duplicate_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parse_status: Mapped[str] = mapped_column(String(32), default="pending")
    review_status: Mapped[str] = mapped_column(String(32), default="pending")
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QuestionBankItem(Base, ManagedEntityMixin):
    __tablename__ = "question_bank_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), index=True)
    canonical_stem: Mapped[str] = mapped_column(Text)
    canonical_options_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    canonical_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_type: Mapped[str] = mapped_column(String(64))
    difficulty_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="draft")


class QuestionSourceLink(Base, ManagedEntityMixin):
    __tablename__ = "question_source_links"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    bank_question_id: Mapped[int] = mapped_column(ForeignKey("question_bank_items.id"), index=True)
    exam_question_id: Mapped[int] = mapped_column(ForeignKey("exam_questions.id"), index=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("exam_papers.id"), index=True)
    source_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_region: Mapped[str | None] = mapped_column(String(64), nullable=True)


class QuestionKnowledgeLink(Base, ManagedEntityMixin):
    __tablename__ = "question_knowledge_links"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("exam_questions.id"), index=True)
    question_layer: Mapped[str] = mapped_column(String(32), default="raw")
    knowledge_point_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), index=True)
    link_type: Mapped[str] = mapped_column(String(32))
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    tag_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    review_status: Mapped[str] = mapped_column(String(32), default="pending")
    reviewed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
