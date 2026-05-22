from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ManagedEntityMixin


LARGE_TEXT = Text().with_variant(mysql.LONGTEXT(), "mysql")


class QuestionBankItem(Base, ManagedEntityMixin):
    __tablename__ = "question_bank_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id"), nullable=True, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("subject_categories.id"), nullable=True, index=True)
    parent_question_id: Mapped[int | None] = mapped_column(
        ForeignKey("question_bank_items.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    question_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    content_fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    node_role: Mapped[str] = mapped_column(String(32), default="standalone", index=True)
    question_type: Mapped[str] = mapped_column(String(64), index=True)
    group_stem: Mapped[str | None] = mapped_column(LARGE_TEXT, nullable=True)
    material_text: Mapped[str | None] = mapped_column(LARGE_TEXT, nullable=True)
    stem_text: Mapped[str] = mapped_column(LARGE_TEXT)
    options_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    answer_text: Mapped[str | None] = mapped_column(LARGE_TEXT, nullable=True)
    analysis_text: Mapped[str | None] = mapped_column(LARGE_TEXT, nullable=True)
    difficulty_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    first_source_question_id: Mapped[int | None] = mapped_column(
        ForeignKey("paper_review_questions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class QuestionBankSourceLink(Base, ManagedEntityMixin):
    __tablename__ = "question_bank_source_links"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    bank_question_id: Mapped[int] = mapped_column(ForeignKey("question_bank_items.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(64), default="paper_review_question", index=True)
    source_question_id: Mapped[int] = mapped_column(ForeignKey("paper_review_questions.id", ondelete="CASCADE"), index=True)
    paper_id: Mapped[int | None] = mapped_column(ForeignKey("exam_papers.id", ondelete="SET NULL"), nullable=True, index=True)
    section_id: Mapped[int | None] = mapped_column(ForeignKey("paper_sections.id", ondelete="SET NULL"), nullable=True)
    question_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
