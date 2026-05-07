from __future__ import annotations

from collections import Counter, defaultdict

from sqlalchemy import select

from app.models import AnalysisJob, AnalysisReport, ExamPaper, ExamQuestion, KnowledgePoint, QuestionKnowledgeLink, Subject
from app.repositories.base import Repository


class AnalysisRepository(Repository):
    def list_jobs(self) -> list[AnalysisJob]:
        return list(self.session.scalars(select(AnalysisJob).order_by(AnalysisJob.id.desc())))

    def get_job(self, job_id: int) -> AnalysisJob | None:
        return self.session.get(AnalysisJob, job_id)

    def list_reports(self) -> list[AnalysisReport]:
        return list(self.session.scalars(select(AnalysisReport).order_by(AnalysisReport.id.desc())))

    def list_subjects(self) -> list[Subject]:
        return list(self.session.scalars(select(Subject).order_by(Subject.id.asc())))

    def list_papers(self) -> list[ExamPaper]:
        return list(self.session.scalars(select(ExamPaper).order_by(ExamPaper.id.asc())))

    def list_questions(self) -> list[ExamQuestion]:
        return list(self.session.scalars(select(ExamQuestion).order_by(ExamQuestion.id.asc())))

    def list_knowledge_points(self) -> list[KnowledgePoint]:
        return list(self.session.scalars(select(KnowledgePoint).order_by(KnowledgePoint.id.asc())))

    def list_question_knowledge_links(self) -> list[QuestionKnowledgeLink]:
        return list(self.session.scalars(select(QuestionKnowledgeLink).order_by(QuestionKnowledgeLink.id.asc())))

    def create_report(self, report: AnalysisReport) -> AnalysisReport:
        self.session.add(report)
        self.session.flush()
        return report

    def get_report(self, report_id: int) -> AnalysisReport | None:
        return self.session.get(AnalysisReport, report_id)
