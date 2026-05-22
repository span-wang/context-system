"""add learning tables

Revision ID: 4d5e6f7a8b9c
Revises: 3c4d5e6f7a8b
Create Date: 2026-05-14 12:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "4d5e6f7a8b9c"
down_revision = "3c4d5e6f7a8b"
branch_labels = None
depends_on = None


LONGTEXT = sa.Text().with_variant(mysql.LONGTEXT(), "mysql")


def upgrade() -> None:
    _rename_table_if_incompatible(
        "practice_sessions",
        {"user_id", "answer_mode", "title", "status", "total_count", "tenant_id"},
    )
    _rename_table_if_incompatible(
        "practice_session_items",
        {"session_id", "question_snapshot_json", "tenant_id"},
    )
    _rename_table_if_incompatible(
        "practice_answers",
        {"session_id", "session_item_id", "marked", "tenant_id"},
    )
    _rename_table_if_incompatible(
        "wrong_book_items",
        {"user_id", "question_snapshot_json", "wrong_count", "tenant_id"},
    )

    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())
    if "practice_sessions" not in existing_tables:
        op.create_table(
            "practice_sessions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("session_type", sa.String(length=32), nullable=False),
            sa.Column("answer_mode", sa.String(length=32), nullable=False),
            sa.Column("subject_id", sa.Integer(), nullable=True),
            sa.Column("category_id", sa.Integer(), nullable=True),
            sa.Column("chapter_id", sa.Integer(), nullable=True),
            sa.Column("paper_id", sa.Integer(), nullable=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("filters_json", sa.JSON(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("total_count", sa.Integer(), nullable=False),
            sa.Column("answered_count", sa.Integer(), nullable=False),
            sa.Column("correct_count", sa.Integer(), nullable=False),
            sa.Column("accuracy_rate", sa.Numeric(precision=5, scale=2), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("duration_seconds", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["category_id"], ["subject_categories.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["paper_id"], ["exam_papers.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("practice_sessions", op.f("ix_practice_sessions_user_id"), ["user_id"])
    _create_index_if_missing("practice_sessions", op.f("ix_practice_sessions_session_type"), ["session_type"])
    _create_index_if_missing("practice_sessions", op.f("ix_practice_sessions_answer_mode"), ["answer_mode"])
    _create_index_if_missing("practice_sessions", op.f("ix_practice_sessions_subject_id"), ["subject_id"])
    _create_index_if_missing("practice_sessions", op.f("ix_practice_sessions_category_id"), ["category_id"])
    _create_index_if_missing("practice_sessions", op.f("ix_practice_sessions_chapter_id"), ["chapter_id"])
    _create_index_if_missing("practice_sessions", op.f("ix_practice_sessions_paper_id"), ["paper_id"])
    _create_index_if_missing("practice_sessions", op.f("ix_practice_sessions_status"), ["status"])
    _create_index_if_missing("practice_sessions", op.f("ix_practice_sessions_tenant_id"), ["tenant_id"])

    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())
    if "practice_session_items" not in existing_tables:
        op.create_table(
            "practice_session_items",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("session_id", sa.Integer(), nullable=False),
            sa.Column("bank_question_id", sa.Integer(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.Column("score", sa.Integer(), nullable=False),
            sa.Column("question_snapshot_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["bank_question_id"], ["question_bank_items.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["session_id"], ["practice_sessions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("practice_session_items", op.f("ix_practice_session_items_session_id"), ["session_id"])
    _create_index_if_missing("practice_session_items", op.f("ix_practice_session_items_bank_question_id"), ["bank_question_id"])
    _create_index_if_missing("practice_session_items", op.f("ix_practice_session_items_tenant_id"), ["tenant_id"])

    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())
    if "practice_answers" not in existing_tables:
        op.create_table(
            "practice_answers",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("session_id", sa.Integer(), nullable=False),
            sa.Column("session_item_id", sa.Integer(), nullable=False),
            sa.Column("bank_question_id", sa.Integer(), nullable=True),
            sa.Column("learner_answer", LONGTEXT, nullable=True),
            sa.Column("is_correct", sa.Boolean(), nullable=True),
            sa.Column("marked", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("spent_seconds", sa.Integer(), nullable=True),
            sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["bank_question_id"], ["question_bank_items.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["session_id"], ["practice_sessions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["session_item_id"], ["practice_session_items.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("session_item_id", name="uq_practice_answers_session_item_id"),
        )
    _create_index_if_missing("practice_answers", op.f("ix_practice_answers_session_id"), ["session_id"])
    _create_index_if_missing("practice_answers", op.f("ix_practice_answers_session_item_id"), ["session_item_id"], unique=True)
    _create_index_if_missing("practice_answers", op.f("ix_practice_answers_bank_question_id"), ["bank_question_id"])
    _create_index_if_missing("practice_answers", op.f("ix_practice_answers_tenant_id"), ["tenant_id"])

    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())
    if "wrong_book_items" not in existing_tables:
        op.create_table(
            "wrong_book_items",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("bank_question_id", sa.Integer(), nullable=True),
            sa.Column("source_session_id", sa.Integer(), nullable=True),
            sa.Column("question_snapshot_json", sa.JSON(), nullable=False),
            sa.Column("wrong_count", sa.Integer(), nullable=False),
            sa.Column("correct_streak", sa.Integer(), nullable=False),
            sa.Column("mastered", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("last_wrong_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_practiced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["bank_question_id"], ["question_bank_items.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["source_session_id"], ["practice_sessions.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "bank_question_id", name="uq_wrong_book_user_question"),
        )
    _create_index_if_missing("wrong_book_items", op.f("ix_wrong_book_items_user_id"), ["user_id"])
    _create_index_if_missing("wrong_book_items", op.f("ix_wrong_book_items_bank_question_id"), ["bank_question_id"])
    _create_index_if_missing("wrong_book_items", op.f("ix_wrong_book_items_source_session_id"), ["source_session_id"])
    _create_index_if_missing("wrong_book_items", op.f("ix_wrong_book_items_mastered"), ["mastered"])
    _create_index_if_missing("wrong_book_items", op.f("ix_wrong_book_items_tenant_id"), ["tenant_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())
    for table_name in ("wrong_book_items", "practice_answers", "practice_session_items", "practice_sessions"):
        if table_name in existing_tables:
            op.drop_table(table_name)
            existing_tables.remove(table_name)


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str], *, unique: bool = False) -> None:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    if not set(columns).issubset(existing_columns):
        return
    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name in existing_indexes:
        return
    op.create_index(index_name, table_name, columns, unique=unique)


def _rename_table_if_incompatible(table_name: str, required_columns: set[str]) -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())
    if table_name not in existing_tables:
        return
    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    if required_columns.issubset(existing_columns):
        return
    op.rename_table(table_name, _next_legacy_table_name(table_name, existing_tables))


def _next_legacy_table_name(table_name: str, existing_tables: set[str]) -> str:
    candidate = f"{table_name}_legacy"
    if candidate not in existing_tables:
        return candidate
    suffix = 2
    while True:
        candidate = f"{table_name}_legacy_{suffix}"
        if candidate not in existing_tables:
            return candidate
        suffix += 1
