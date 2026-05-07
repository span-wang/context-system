from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.workflow import WorkflowRepository
from app.schemas.workflow import ReviewTaskResponse, WorkflowTopicResponse


class AnalysisToTopicService:
    def __init__(self, session: Session) -> None:
        self.repository = WorkflowRepository(session)

    def list_review_tasks(self) -> list[ReviewTaskResponse]:
        return [ReviewTaskResponse.model_validate(item) for item in self.repository.list_review_tasks()]

    def list_topics(self) -> list[WorkflowTopicResponse]:
        reports = self.repository.list_reports()
        tasks = self.repository.list_review_tasks()
        rows: list[WorkflowTopicResponse] = []
        for index, report in enumerate(reports):
            task = tasks[index] if index < len(tasks) else None
            rows.append(
                WorkflowTopicResponse(
                    title=f"基于《{report.report_name}》生成冲刺内容",
                    source_report=report.report_name,
                    task_type=task.task_type if task else "content_generation",
                    priority=task.priority if task else "medium",
                    status=task.status if task else "planned",
                )
            )
        return rows
