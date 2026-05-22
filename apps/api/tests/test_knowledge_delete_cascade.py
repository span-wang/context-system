from __future__ import annotations

from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models import Chapter, KnowledgePoint, Subject, SubjectCategory, Tenant
from app.models.base import Base
from app.services.knowledge import KnowledgeTreeService


def _sqlite_session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def _seed_subject_tree(session: Session) -> tuple[Tenant, Subject, SubjectCategory]:
    tenant = Tenant(code="tenant-1", name="Tenant 1", status="active", plan_type="professional")
    session.add(tenant)
    session.flush()

    subject = Subject(tenant_id=tenant.id, code="acct", name="会计", status="active")
    session.add(subject)
    session.flush()

    category = SubjectCategory(tenant_id=tenant.id, subject_id=subject.id, name="基础", sort_order=1)
    session.add(category)
    session.flush()
    return tenant, subject, category


def test_delete_chapter_removes_nested_chapters_leaf_first_for_mysql_compatible_constraints() -> None:
    engine, session_factory = _sqlite_session_factory()

    @event.listens_for(engine, "before_cursor_execute")
    def _simulate_mysql_chapter_self_fk(conn, cursor, statement, parameters, context, executemany) -> None:
        normalized = statement.lstrip().upper()
        if normalized.startswith("DELETE FROM CHAPTERS") and not executemany and len(parameters) > 1:
            raise IntegrityError(statement, parameters, Exception("simulated mysql chapter self-fk failure"))

    session = session_factory()
    try:
        tenant, subject, category = _seed_subject_tree(session)
        chapter = Chapter(
            tenant_id=tenant.id,
            subject_id=subject.id,
            category_id=category.id,
            parent_id=None,
            name="第一章",
            level=1,
            path="第一章",
            sort_order=1,
        )
        session.add(chapter)
        session.flush()

        section = Chapter(
            tenant_id=tenant.id,
            subject_id=subject.id,
            category_id=category.id,
            parent_id=chapter.id,
            name="第一节",
            level=2,
            path="第一章 / 第一节",
            sort_order=1,
        )
        session.add(section)
        session.commit()

        result = KnowledgeTreeService(session).delete_chapter(chapter.id)

        assert result.removed_chapter_count == 2
        assert session.query(Chapter).count() == 0
    finally:
        session.close()
        engine.dispose()


def test_delete_chapter_clears_legacy_mastery_snapshots_before_deleting_points() -> None:
    engine, session_factory = _sqlite_session_factory()
    session = session_factory()
    try:
        session.execute(
            text(
                "CREATE TABLE mastery_snapshots ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "knowledge_point_id INTEGER NOT NULL REFERENCES knowledge_points (id)"
                ")"
            )
        )
        tenant, subject, category = _seed_subject_tree(session)
        chapter = Chapter(
            tenant_id=tenant.id,
            subject_id=subject.id,
            category_id=category.id,
            parent_id=None,
            name="第一章",
            level=1,
            path="第一章",
            sort_order=1,
        )
        session.add(chapter)
        session.flush()

        point = KnowledgePoint(
            tenant_id=tenant.id,
            subject_id=subject.id,
            category_id=category.id,
            chapter_id=chapter.id,
            parent_id=None,
            name="资产",
            level=1,
            path="第一章 / 资产",
            description=None,
            keywords_json=None,
            status="active",
            sort_order=1,
        )
        session.add(point)
        session.flush()
        session.execute(
            text("INSERT INTO mastery_snapshots (knowledge_point_id) VALUES (:knowledge_point_id)"),
            {"knowledge_point_id": point.id},
        )
        session.commit()

        result = KnowledgeTreeService(session).delete_chapter(chapter.id)

        assert result.unbound_point_count == 1
        assert session.query(Chapter).count() == 0
        assert session.query(KnowledgePoint).count() == 0
        assert session.execute(text("SELECT COUNT(*) FROM mastery_snapshots")).scalar_one() == 0
    finally:
        session.close()
        engine.dispose()


def test_delete_chapter_removes_nested_points_leaf_first_for_mysql_compatible_constraints() -> None:
    engine, session_factory = _sqlite_session_factory()

    @event.listens_for(engine, "before_cursor_execute")
    def _simulate_mysql_point_self_fk(conn, cursor, statement, parameters, context, executemany) -> None:
        normalized = statement.lstrip().upper()
        if normalized.startswith("DELETE FROM KNOWLEDGE_POINTS") and not executemany and len(parameters) > 1:
            raise IntegrityError(statement, parameters, Exception("simulated mysql point self-fk failure"))

    session = session_factory()
    try:
        tenant, subject, category = _seed_subject_tree(session)
        chapter = Chapter(
            tenant_id=tenant.id,
            subject_id=subject.id,
            category_id=category.id,
            parent_id=None,
            name="第一章",
            level=1,
            path="第一章",
            sort_order=1,
        )
        session.add(chapter)
        session.flush()

        point = KnowledgePoint(
            tenant_id=tenant.id,
            subject_id=subject.id,
            category_id=category.id,
            chapter_id=chapter.id,
            parent_id=None,
            name="资产",
            level=1,
            path="第一章 / 资产",
            description=None,
            keywords_json=None,
            status="active",
            sort_order=1,
        )
        session.add(point)
        session.flush()

        detail = KnowledgePoint(
            tenant_id=tenant.id,
            subject_id=subject.id,
            category_id=category.id,
            chapter_id=chapter.id,
            parent_id=point.id,
            name="流动资产",
            level=2,
            path="第一章 / 资产 / 流动资产",
            description=None,
            keywords_json=None,
            status="active",
            sort_order=1,
        )
        session.add(detail)
        session.commit()

        result = KnowledgeTreeService(session).delete_chapter(chapter.id)

        assert result.unbound_point_count == 2
        assert session.query(KnowledgePoint).count() == 0
        assert session.query(Chapter).count() == 0
    finally:
        session.close()
        engine.dispose()
