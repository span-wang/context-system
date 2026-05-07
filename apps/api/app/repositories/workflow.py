from __future__ import annotations

from sqlalchemy import select

from app.models import AnalysisReport, ReviewTask
from app.repositories.base import Repository


class WorkflowRepository(Repository):
    def list_review_tasks(self) -> list[ReviewTask]:
        return list(self.session.scalars(select(ReviewTask).order_by(ReviewTask.priority.desc(), ReviewTask.id.asc())))

    def list_reports(self) -> list[AnalysisReport]:
        return list(self.session.scalars(select(AnalysisReport).order_by(AnalysisReport.id.desc())))
