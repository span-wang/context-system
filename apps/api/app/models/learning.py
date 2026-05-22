from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ManagedEntityMixin


LARGE_TEXT = Text().with_variant(mysql.LONGTEXT(), "mysql")


class PracticeSession(Base, ManagedEntityMixin):
    __tablename__ = "practice_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_type: Mapped[str] = mapped_column(String(32), index=True)
    answer_mode: Mapped[str] = mapped_column(String(32), index=True)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True, index=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("subject_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True, index=True)
    paper_id: Mapped[int | None] = mapped_column(ForeignKey("exam_papers.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    filters_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="in_progress", index=True)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    answered_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    accuracy_rate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PracticeSessionItem(Base, ManagedEntityMixin):
    __tablename__ = "practice_session_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("practice_sessions.id", ondelete="CASCADE"), index=True)
    bank_question_id: Mapped[int | None] = mapped_column(
        ForeignKey("question_bank_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[int] = mapped_column(Integer, default=1)
    question_snapshot_json: Mapped[dict[str, object]] = mapped_column(JSON)


class PracticeAnswer(Base, ManagedEntityMixin):
    __tablename__ = "practice_answers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("practice_sessions.id", ondelete="CASCADE"), index=True)
    session_item_id: Mapped[int] = mapped_column(ForeignKey("practice_session_items.id", ondelete="CASCADE"), index=True, unique=True)
    bank_question_id: Mapped[int | None] = mapped_column(
        ForeignKey("question_bank_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    learner_answer: Mapped[str | None] = mapped_column(LARGE_TEXT, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    marked: Mapped[bool] = mapped_column(Boolean, default=False)
    wrong_reason_tags_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    reflection_note: Mapped[str | None] = mapped_column(LARGE_TEXT, nullable=True)
    spent_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WrongBookItem(Base, ManagedEntityMixin):
    __tablename__ = "wrong_book_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    bank_question_id: Mapped[int | None] = mapped_column(
        ForeignKey("question_bank_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("practice_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    question_snapshot_json: Mapped[dict[str, object]] = mapped_column(JSON)
    wrong_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_streak: Mapped[int] = mapped_column(Integer, default=0)
    mastered: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_wrong_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_practiced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MasterySnapshot(Base, ManagedEntityMixin):
    __tablename__ = "mastery_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    knowledge_point_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id", ondelete="CASCADE"), index=True)
    mastery_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    answered_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    snapshot_date: Mapped[date] = mapped_column(Date)
    last_practiced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
