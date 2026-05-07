from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ManagedEntityMixin


class Subject(Base, ManagedEntityMixin):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="active")


class SubjectCategory(Base, ManagedEntityMixin):
    __tablename__ = "subject_categories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Chapter(Base, ManagedEntityMixin):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(128))
    level: Mapped[int] = mapped_column(Integer, default=1)
    path: Mapped[str] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class KnowledgePoint(Base, ManagedEntityMixin):
    __tablename__ = "knowledge_points"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("subject_categories.id"), nullable=True)
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id"), nullable=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_points.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(128))
    level: Mapped[int] = mapped_column(Integer, default=1)
    path: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class KnowledgePointAlias(Base, ManagedEntityMixin):
    __tablename__ = "knowledge_point_aliases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    knowledge_point_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), index=True)
    alias_name: Mapped[str] = mapped_column(String(128))


class KnowledgePointRelation(Base, ManagedEntityMixin):
    __tablename__ = "knowledge_point_relations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    from_kp_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), index=True)
    to_kp_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), index=True)
    relation_type: Mapped[str] = mapped_column(String(64))
