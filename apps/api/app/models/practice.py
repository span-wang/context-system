from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ManagedEntityMixin


class PracticeSet(Base, ManagedEntityMixin):
    __tablename__ = "practice_sets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), index=True)
    set_type: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_report_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_reports.id"), nullable=True)
    difficulty_policy: Mapped[str | None] = mapped_column(String(64), nullable=True)
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="draft")


class PracticeSetQuestion(Base, ManagedEntityMixin):
    __tablename__ = "practice_set_questions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    practice_set_id: Mapped[int] = mapped_column(ForeignKey("practice_sets.id"), index=True)
    bank_question_id: Mapped[int] = mapped_column(ForeignKey("question_bank_items.id"), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)


class MockExam(Base, ManagedEntityMixin):
    __tablename__ = "mock_exams"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    exam_mode: Mapped[str] = mapped_column(String(64))
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")


class MockExamQuestion(Base, ManagedEntityMixin):
    __tablename__ = "mock_exam_questions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    mock_exam_id: Mapped[int] = mapped_column(ForeignKey("mock_exams.id"), index=True)
    bank_question_id: Mapped[int] = mapped_column(ForeignKey("question_bank_items.id"), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)


class LearnerProfile(Base, ManagedEntityMixin):
    __tablename__ = "learner_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    target_exam: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preferred_subjects_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)


class PracticeSession(Base, ManagedEntityMixin):
    __tablename__ = "practice_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    learner_id: Mapped[int] = mapped_column(ForeignKey("learner_profiles.id"), index=True)
    session_type: Mapped[str] = mapped_column(String(64))
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id"), nullable=True, index=True)
    practice_set_id: Mapped[int | None] = mapped_column(ForeignKey("practice_sets.id"), nullable=True)
    mock_exam_id: Mapped[int | None] = mapped_column(ForeignKey("mock_exams.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accuracy_rate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PracticeAnswer(Base, ManagedEntityMixin):
    __tablename__ = "practice_answers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("practice_sessions.id"), index=True)
    bank_question_id: Mapped[int] = mapped_column(ForeignKey("question_bank_items.id"), index=True)
    learner_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    spent_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    knowledge_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class WrongBookItem(Base, ManagedEntityMixin):
    __tablename__ = "wrong_book_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    learner_id: Mapped[int] = mapped_column(ForeignKey("learner_profiles.id"), index=True)
    bank_question_id: Mapped[int] = mapped_column(ForeignKey("question_bank_items.id"), index=True)
    source_session_id: Mapped[int | None] = mapped_column(ForeignKey("practice_sessions.id"), nullable=True)
    wrong_count: Mapped[int] = mapped_column(Integer, default=0)
    last_wrong_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mastered: Mapped[bool] = mapped_column(Boolean, default=False)


class Favorite(Base, ManagedEntityMixin):
    __tablename__ = "favorites"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    learner_id: Mapped[int] = mapped_column(ForeignKey("learner_profiles.id"), index=True)
    bank_question_id: Mapped[int] = mapped_column(ForeignKey("question_bank_items.id"), index=True)


class MasterySnapshot(Base, ManagedEntityMixin):
    __tablename__ = "mastery_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    learner_id: Mapped[int] = mapped_column(ForeignKey("learner_profiles.id"), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), index=True)
    knowledge_point_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), index=True)
    mastery_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    answered_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    snapshot_date: Mapped[date] = mapped_column(Date)
