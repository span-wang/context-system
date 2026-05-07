from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ManagedEntityMixin


class AnalysisJob(Base, ManagedEntityMixin):
    __tablename__ = "analysis_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(64))
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id"), nullable=True, index=True)
    scope_type: Mapped[str] = mapped_column(String(64))
    scope_config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    result_summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AnalysisReport(Base, ManagedEntityMixin):
    __tablename__ = "analysis_reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id"), nullable=True, index=True)
    report_type: Mapped[str] = mapped_column(String(64))
    report_name: Mapped[str] = mapped_column(String(255))
    scope_config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    filters_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    snapshot_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    report_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
