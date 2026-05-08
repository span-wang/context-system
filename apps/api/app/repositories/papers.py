from __future__ import annotations

from sqlalchemy import func, select

from app.models import (
    AnalysisJob,
    Asset,
    ExamPaper,
    ExamQuestion,
    KnowledgePoint,
    PaperSection,
    QuestionBankItem,
    QuestionKnowledgeLink,
    QuestionSourceLink,
    ReviewTask,
    Subject,
    SubjectCategory,
    Tenant,
    User,
)
from app.repositories.base import Repository


class PaperRepository(Repository):
    def list_papers(self) -> list[ExamPaper]:
        stmt = select(ExamPaper).order_by(ExamPaper.exam_year.desc(), ExamPaper.id.desc())
        return list(self.session.scalars(stmt))

    def get_paper(self, paper_id: int) -> ExamPaper | None:
        return self.session.get(ExamPaper, paper_id)

    def find_active_parse_job(self, paper_id: int) -> AnalysisJob | None:
        return self.find_active_job(paper_id, "paper_parse")

    def find_active_job(self, paper_id: int, job_type: str) -> AnalysisJob | None:
        stmt = (
            select(AnalysisJob)
            .where(
                AnalysisJob.job_type == job_type,
                AnalysisJob.scope_type == "paper",
                AnalysisJob.status.in_(("pending", "running")),
            )
            .order_by(AnalysisJob.id.desc())
        )
        for job in self.session.scalars(stmt):
            if (job.scope_config_json or {}).get("paper_id") == paper_id:
                return job
        return None

    def list_parse_jobs(self, paper_id: int) -> list[AnalysisJob]:
        return self.list_jobs(paper_id, job_type="paper_parse")

    def list_jobs(self, paper_id: int, job_type: str | None = None) -> list[AnalysisJob]:
        stmt = select(AnalysisJob).where(AnalysisJob.scope_type == "paper")
        if job_type is not None:
            stmt = stmt.where(AnalysisJob.job_type == job_type)
        stmt = stmt.order_by(AnalysisJob.id.desc())
        jobs: list[AnalysisJob] = []
        for job in self.session.scalars(stmt):
            if (job.scope_config_json or {}).get("paper_id") == paper_id:
                jobs.append(job)
        return jobs

    def list_sections(self, paper_id: int) -> list[PaperSection]:
        stmt = select(PaperSection).where(PaperSection.paper_id == paper_id).order_by(PaperSection.sort_order.asc())
        return list(self.session.scalars(stmt))

    def get_asset(self, asset_id: int | None) -> Asset | None:
        if asset_id is None:
            return None
        return self.session.get(Asset, asset_id)

    def get_subject(self, subject_id: int | None) -> Subject | None:
        if subject_id is None:
            return None
        return self.session.get(Subject, subject_id)

    def get_default_tenant(self, code: str) -> Tenant | None:
        return self.session.scalar(select(Tenant).where(Tenant.code == code))

    def get_default_user(self, tenant_id: int) -> User | None:
        stmt = select(User).where(User.tenant_id == tenant_id).order_by(User.id.asc())
        return self.session.scalar(stmt)

    def get_subject_by_id(self, subject_id: int) -> Subject | None:
        return self.session.get(Subject, subject_id)

    def get_subject_category(self, category_id: int | None) -> SubjectCategory | None:
        if category_id is None:
            return None
        return self.session.get(SubjectCategory, category_id)

    def get_subject_by_code_or_name(self, code: str | None, name: str | None) -> Subject | None:
        normalized_code = (code or "").strip()
        normalized_name = (name or "").strip()
        if not normalized_code and not normalized_name:
            return None
        stmt = select(Subject)
        if normalized_code and normalized_name:
            stmt = stmt.where((Subject.code == normalized_code) | (Subject.name == normalized_name))
        elif normalized_code:
            stmt = stmt.where(Subject.code == normalized_code)
        else:
            stmt = stmt.where(Subject.name == normalized_name)
        return self.session.scalar(stmt.order_by(Subject.id.asc()))

    def create_subject(self, subject: Subject) -> Subject:
        self.session.add(subject)
        self.session.flush()
        return subject

    def ensure_subject_category(
        self,
        tenant_id: int,
        subject_id: int,
        name: str,
        operator_id: int | None,
    ) -> SubjectCategory:
        normalized_name = name.strip()
        existing = self.session.scalar(
            select(SubjectCategory)
            .where(SubjectCategory.subject_id == subject_id, SubjectCategory.name == normalized_name)
            .order_by(SubjectCategory.id.asc())
        )
        if existing:
            return existing
        max_sort_order = self.session.scalar(
            select(func.max(SubjectCategory.sort_order)).where(SubjectCategory.subject_id == subject_id)
        ) or 0
        category = SubjectCategory(
            tenant_id=tenant_id,
            subject_id=subject_id,
            name=normalized_name,
            sort_order=max_sort_order + 1,
            created_by=operator_id,
            updated_by=operator_id,
        )
        self.session.add(category)
        self.session.flush()
        return category

    def get_asset_by_sha(self, sha256: str) -> Asset | None:
        return self.session.scalar(select(Asset).where(Asset.sha256 == sha256))

    def get_paper_by_asset(self, asset_id: int) -> ExamPaper | None:
        return self.session.scalar(select(ExamPaper).where(ExamPaper.asset_id == asset_id))

    def create_asset(self, asset: Asset) -> Asset:
        self.session.add(asset)
        self.session.flush()
        return asset

    def create_paper(self, paper: ExamPaper) -> ExamPaper:
        self.session.add(paper)
        self.session.flush()
        return paper

    def list_questions(self, paper_id: int) -> list[ExamQuestion]:
        stmt = select(ExamQuestion).where(ExamQuestion.paper_id == paper_id).order_by(ExamQuestion.id.asc())
        return list(self.session.scalars(stmt))

    def list_knowledge_points(self, subject_id: int | None = None) -> list[KnowledgePoint]:
        stmt = select(KnowledgePoint)
        if subject_id is not None:
            stmt = stmt.where(KnowledgePoint.subject_id == subject_id)
        stmt = stmt.order_by(KnowledgePoint.sort_order.asc(), KnowledgePoint.id.asc())
        return list(self.session.scalars(stmt))

    def delete_parse_outputs(self, paper_id: int) -> None:
        question_ids = [
            row[0]
            for row in self.session.query(ExamQuestion.id)
            .filter(ExamQuestion.paper_id == paper_id)
            .all()
        ]
        if question_ids:
            self.session.query(QuestionKnowledgeLink).filter(
                QuestionKnowledgeLink.question_id.in_(question_ids)
            ).delete(synchronize_session=False)
            self.session.query(ExamQuestion).filter(
                ExamQuestion.id.in_(question_ids)
            ).delete(synchronize_session=False)
        self.session.query(PaperSection).filter(PaperSection.paper_id == paper_id).delete(synchronize_session=False)

    def create_section(self, section: PaperSection) -> PaperSection:
        self.session.add(section)
        self.session.flush()
        return section

    def create_questions(self, questions: list[ExamQuestion]) -> list[ExamQuestion]:
        self.session.add_all(questions)
        self.session.flush()
        return questions

    def count_source_links(self, paper_id: int) -> int:
        stmt = select(func.count()).select_from(QuestionSourceLink).where(QuestionSourceLink.paper_id == paper_id)
        return int(self.session.scalar(stmt) or 0)

    def delete_paper(self, paper_id: int) -> None:
        question_ids = [
            row[0]
            for row in self.session.query(ExamQuestion.id)
            .filter(ExamQuestion.paper_id == paper_id)
            .all()
        ]
        source_links = list(
            self.session.query(QuestionSourceLink)
            .filter(QuestionSourceLink.paper_id == paper_id)
            .all()
        )
        if source_links:
            source_counts: dict[int, int] = {}
            for link in source_links:
                source_counts[link.bank_question_id] = source_counts.get(link.bank_question_id, 0) + 1
            for bank_question_id, removed_count in source_counts.items():
                bank_item = self.session.get(QuestionBankItem, bank_question_id)
                if bank_item:
                    bank_item.source_count = max(0, bank_item.source_count - removed_count)
            self.session.query(QuestionSourceLink).filter(
                QuestionSourceLink.paper_id == paper_id
            ).delete(synchronize_session=False)
        if question_ids:
            self.session.query(QuestionKnowledgeLink).filter(
                QuestionKnowledgeLink.question_id.in_(question_ids)
            ).delete(synchronize_session=False)
            self.session.query(ReviewTask).filter(
                ReviewTask.target_type.in_(("exam_question", "question")),
                ReviewTask.target_id.in_([str(question_id) for question_id in question_ids]),
            ).delete(synchronize_session=False)
            self.session.query(ExamQuestion).filter(
                ExamQuestion.id.in_(question_ids)
            ).delete(synchronize_session=False)
        self.session.query(ReviewTask).filter(
            ReviewTask.target_type.in_(("paper", "exam_paper")),
            ReviewTask.target_id == str(paper_id),
        ).delete(synchronize_session=False)
        self.session.query(PaperSection).filter(PaperSection.paper_id == paper_id).delete(synchronize_session=False)
        self.session.query(ExamPaper).filter(ExamPaper.id == paper_id).delete(synchronize_session=False)
