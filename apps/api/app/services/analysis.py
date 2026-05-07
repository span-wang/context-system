from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import AnalysisReport
from app.repositories.analysis import AnalysisRepository
from app.repositories.workflow import WorkflowRepository
from app.schemas.analysis import (
    AnalysisJobResponse,
    DashboardFocusItem,
    DashboardMetric,
    DashboardResponse,
    FrequencyResponse,
    GenerateReportRequest,
    ReportResponse,
    TrendResponse,
)


class FrequencyAnalysisService:
    def __init__(self, session: Session) -> None:
        self.repository = AnalysisRepository(session)
        self.workflow_repository = WorkflowRepository(session)

    def get_dashboard(self) -> DashboardResponse:
        subjects = self.repository.list_subjects()
        papers = self.repository.list_papers()
        questions = self.repository.list_questions()
        reports = self.repository.list_reports()
        review_tasks = self.workflow_repository.list_review_tasks()
        focus_points = self.list_frequencies()[:5]
        metrics = [
            DashboardMetric(key="subjects", label="学科数", value=str(len(subjects)), trend="底座已预留多租户"),
            DashboardMetric(key="papers", label="试卷数", value=str(len(papers)), trend="已接入试卷中心"),
            DashboardMetric(key="questions", label="原始题数", value=str(len(questions)), trend="支持原始题/标准题分层"),
            DashboardMetric(key="reports", label="分析报告数", value=str(len(reports)), trend="报告中心已通路由"),
        ]
        return DashboardResponse(
            metrics=metrics,
            focus_points=[
                DashboardFocusItem(
                    knowledge_point_id=item.knowledge_point_id,
                    knowledge_point_name=item.knowledge_point_name,
                    frequency=item.question_count,
                    paper_coverage=item.paper_count,
                    hot_score=item.hot_score,
                )
                for item in focus_points
            ],
            pending_reviews=sum(1 for item in review_tasks if item.status != "completed"),
            latest_report_name=reports[0].report_name if reports else None,
        )

    def list_frequencies(self) -> list[FrequencyResponse]:
        questions = {question.id: question for question in self.repository.list_questions()}
        knowledge_points = {point.id: point for point in self.repository.list_knowledge_points()}
        link_groups: dict[int, set[int]] = defaultdict(set)
        counts: Counter[int] = Counter()
        for link in self.repository.list_question_knowledge_links():
            counts[link.knowledge_point_id] += 1
            question = questions.get(link.question_id)
            if question is not None:
                link_groups[link.knowledge_point_id].add(question.paper_id)

        rows: list[FrequencyResponse] = []
        for kp_id, question_count in counts.most_common():
            point = knowledge_points.get(kp_id)
            if point is None:
                continue
            paper_count = len(link_groups[kp_id])
            hot_score = round(question_count * 0.65 + paper_count * 0.35, 2)
            rows.append(
                FrequencyResponse(
                    knowledge_point_id=kp_id,
                    knowledge_point_name=point.name,
                    question_count=question_count,
                    paper_count=paper_count,
                    hot_score=hot_score,
                )
            )
        return rows

    def list_trends(self) -> list[TrendResponse]:
        papers = {paper.id: paper for paper in self.repository.list_papers()}
        by_year: Counter[int] = Counter()
        for question in self.repository.list_questions():
            paper = papers.get(question.paper_id)
            year = paper.exam_year if paper and paper.exam_year is not None else 0
            by_year[year] += 1
        rows = []
        for year, count in sorted(by_year.items()):
            rows.append(TrendResponse(label=f"{year} 年", year=year or None, question_count=count))
        return rows

    def list_reports(self) -> list[ReportResponse]:
        return [ReportResponse.model_validate(item) for item in self.repository.list_reports()]

    def get_job(self, job_id: int) -> AnalysisJobResponse:
        job = self.repository.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return AnalysisJobResponse.model_validate(job)

    def generate_report(self, payload: GenerateReportRequest) -> ReportResponse:
        frequencies = self.list_frequencies()
        trends = self.list_trends()
        papers = self.repository.list_papers()
        target_papers = [paper for paper in papers if payload.subject_id is None or paper.subject_id == payload.subject_id]
        report = self.repository.create_report(
            AnalysisReport(
                tenant_id=target_papers[0].tenant_id if target_papers else 1,
                subject_id=payload.subject_id,
                report_type=payload.report_type,
                report_name=payload.report_name or f"{date.today().isoformat()} 高频考点报告",
                scope_config_json={"subject_id": payload.subject_id, "paper_count": len(target_papers)},
                filters_json={"source": "current_questions"},
                snapshot_date=date.today(),
                version_no=1,
                status="ready",
                report_json={
                    "summary": _build_report_summary(frequencies, trends),
                    "top_points": [item.model_dump() for item in frequencies[:10]],
                    "trends": [item.model_dump() for item in trends],
                },
                created_by=None,
                updated_by=None,
            )
        )
        self.repository.session.commit()
        return ReportResponse.model_validate(report)

    def export_report_markdown(self, report_id: int) -> str:
        report = self.repository.get_report(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="报告不存在")
        data = report.report_json or {}
        lines = [
            f"# {report.report_name}",
            "",
            f"- 类型：{report.report_type}",
            f"- 日期：{report.snapshot_date or '-'}",
            f"- 版本：v{report.version_no}",
            "",
            "## 摘要",
            "",
            str(data.get("summary") or "暂无摘要"),
            "",
            "## 高频考点",
            "",
        ]
        for item in data.get("top_points", []) or []:
            lines.append(
                f"- {item.get('knowledge_point_name', '未知考点')}：{item.get('question_count', 0)} 题，覆盖 {item.get('paper_count', 0)} 份试卷"
            )
        lines.extend(["", "## 年度趋势", ""])
        for item in data.get("trends", []) or []:
            lines.append(f"- {item.get('label', '-')}: {item.get('question_count', 0)} 题")
        return "\n".join(lines).strip() + "\n"


def _build_report_summary(frequencies: list[FrequencyResponse], trends: list[TrendResponse]) -> str:
    if not frequencies:
        return "当前还没有足够的考点映射数据，建议先完成题目解析和考点标注。"
    top = "、".join(item.knowledge_point_name for item in frequencies[:3])
    total_questions = sum(item.question_count for item in trends)
    return f"当前已统计 {total_questions} 道原始题，高频考点集中在：{top}。"
