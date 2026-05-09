from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ManagedEntityMixin


LARGE_TEXT = Text().with_variant(mysql.LONGTEXT(), "mysql")


class Asset(Base, ManagedEntityMixin):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id"), nullable=True, index=True)
    asset_type: Mapped[str] = mapped_column(String(32))
    source_type: Mapped[str] = mapped_column(String(32))
    source_title: Mapped[str] = mapped_column(String(255))
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(128))
    storage_path: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(128), index=True)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    parse_status: Mapped[str] = mapped_column(String(32), default="pending")
    ocr_status: Mapped[str] = mapped_column(String(32), default="pending")
    parsed_text: Mapped[str | None] = mapped_column(LARGE_TEXT, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tags_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)


class ExamPaper(Base, ManagedEntityMixin):
    __tablename__ = "exam_papers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id"), nullable=True, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("subject_categories.id"), nullable=True, index=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    paper_name: Mapped[str] = mapped_column(String(255))
    paper_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    exam_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exam_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exam_region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    exam_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    paper_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_channel: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    total_question_count: Mapped[int] = mapped_column(Integer, default=0)
    total_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parsed_version: Mapped[int] = mapped_column(Integer, default=1)
    review_status: Mapped[str] = mapped_column(String(32), default="pending")


class PaperSection(Base, ManagedEntityMixin):
    __tablename__ = "paper_sections"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("exam_papers.id"), index=True)
    section_name: Mapped[str] = mapped_column(String(128))
    question_type: Mapped[str] = mapped_column(String(64))
    start_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
