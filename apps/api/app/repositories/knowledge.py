from __future__ import annotations

from sqlalchemy import select

from app.models import Asset, Chapter, KnowledgePoint, Subject, SubjectCategory, Tenant, User
from app.repositories.base import Repository


class KnowledgeRepository(Repository):
    def list_subjects(self) -> list[Subject]:
        return list(self.session.scalars(select(Subject).order_by(Subject.id.asc())))

    def get_default_tenant(self, code: str) -> Tenant | None:
        return self.session.scalar(select(Tenant).where(Tenant.code == code))

    def get_default_user(self, tenant_id: int) -> User | None:
        stmt = select(User).where(User.tenant_id == tenant_id).order_by(User.id.asc())
        return self.session.scalar(stmt)

    def get_subject(self, subject_id: int) -> Subject | None:
        return self.session.get(Subject, subject_id)

    def create_subject(self, subject: Subject) -> Subject:
        self.session.add(subject)
        self.session.flush()
        return subject

    def list_categories(self, subject_id: int | None = None) -> list[SubjectCategory]:
        stmt = select(SubjectCategory)
        if subject_id is not None:
            stmt = stmt.where(SubjectCategory.subject_id == subject_id)
        stmt = stmt.order_by(SubjectCategory.sort_order.asc(), SubjectCategory.id.asc())
        return list(self.session.scalars(stmt))

    def get_category(self, category_id: int) -> SubjectCategory | None:
        return self.session.get(SubjectCategory, category_id)

    def create_category(self, category: SubjectCategory) -> SubjectCategory:
        self.session.add(category)
        self.session.flush()
        return category

    def list_chapters(self, subject_id: int | None = None) -> list[Chapter]:
        stmt = select(Chapter)
        if subject_id is not None:
            stmt = stmt.where(Chapter.subject_id == subject_id)
        stmt = stmt.order_by(Chapter.sort_order.asc(), Chapter.id.asc())
        return list(self.session.scalars(stmt))

    def get_chapter(self, chapter_id: int) -> Chapter | None:
        return self.session.get(Chapter, chapter_id)

    def create_chapter(self, chapter: Chapter) -> Chapter:
        self.session.add(chapter)
        self.session.flush()
        return chapter

    def list_knowledge_points(self, subject_id: int | None = None) -> list[KnowledgePoint]:
        stmt = select(KnowledgePoint)
        if subject_id is not None:
            stmt = stmt.where(KnowledgePoint.subject_id == subject_id)
        stmt = stmt.order_by(KnowledgePoint.sort_order.asc(), KnowledgePoint.id.asc())
        return list(self.session.scalars(stmt))

    def get_knowledge_point(self, point_id: int) -> KnowledgePoint | None:
        return self.session.get(KnowledgePoint, point_id)

    def create_knowledge_point(self, point: KnowledgePoint) -> KnowledgePoint:
        self.session.add(point)
        self.session.flush()
        return point

    def list_textbooks(self, subject_id: int | None = None) -> list[Asset]:
        stmt = select(Asset).where(Asset.source_type == "textbook")
        if subject_id is not None:
            stmt = stmt.where(Asset.subject_id == subject_id)
        stmt = stmt.order_by(Asset.created_at.desc(), Asset.id.desc())
        return list(self.session.scalars(stmt))

    def get_textbook(self, textbook_id: int) -> Asset | None:
        asset = self.session.get(Asset, textbook_id)
        if asset is None or asset.source_type != "textbook":
            return None
        return asset

    def update_textbook(self, textbook: Asset, data: dict[str, object]) -> Asset:
        for key, value in data.items():
            setattr(textbook, key, value)
        self.session.flush()
        return textbook
