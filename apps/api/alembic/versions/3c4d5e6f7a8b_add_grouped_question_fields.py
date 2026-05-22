"""add grouped question fields

Revision ID: 3c4d5e6f7a8b
Revises: 2b3c4d5e6f7
Create Date: 2026-05-12 09:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "3c4d5e6f7a8b"
down_revision = "2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    long_text = sa.Text().with_variant(mysql.LONGTEXT(), "mysql")

    _add_column_if_missing(
        "paper_review_questions",
        sa.Column("parent_question_id", sa.Integer(), nullable=True),
    )
    _add_column_if_missing(
        "paper_review_questions",
        sa.Column("node_role", sa.String(length=32), nullable=False, server_default="standalone"),
    )
    _add_column_if_missing(
        "paper_review_questions",
        sa.Column("group_stem", long_text, nullable=True),
    )
    _add_column_if_missing(
        "paper_review_questions",
        sa.Column("material_text", long_text, nullable=True),
    )
    _create_index_if_missing("paper_review_questions", op.f("ix_paper_review_questions_parent_question_id"), ["parent_question_id"])
    _create_foreign_key_if_missing(
        "paper_review_questions",
        "fk_paper_review_questions_parent_question_id",
        "paper_review_questions",
        ["parent_question_id"],
        ["id"],
        ondelete="CASCADE",
    )

    _add_column_if_missing(
        "question_bank_items",
        sa.Column("parent_question_id", sa.Integer(), nullable=True),
    )
    _add_column_if_missing(
        "question_bank_items",
        sa.Column("node_role", sa.String(length=32), nullable=False, server_default="standalone"),
    )
    _add_column_if_missing(
        "question_bank_items",
        sa.Column("group_stem", long_text, nullable=True),
    )
    _add_column_if_missing(
        "question_bank_items",
        sa.Column("material_text", long_text, nullable=True),
    )
    _create_index_if_missing("question_bank_items", op.f("ix_question_bank_items_parent_question_id"), ["parent_question_id"])
    _create_index_if_missing("question_bank_items", op.f("ix_question_bank_items_node_role"), ["node_role"])
    _create_foreign_key_if_missing(
        "question_bank_items",
        "fk_question_bank_items_parent_question_id",
        "question_bank_items",
        ["parent_question_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.execute("UPDATE paper_review_questions SET node_role = 'standalone' WHERE node_role IS NULL OR node_role = ''")
    op.execute("UPDATE question_bank_items SET node_role = 'standalone' WHERE node_role IS NULL OR node_role = ''")


def downgrade() -> None:
    _drop_foreign_key_if_exists("question_bank_items", "fk_question_bank_items_parent_question_id")
    _drop_index_if_exists("question_bank_items", op.f("ix_question_bank_items_parent_question_id"))
    _drop_index_if_exists("question_bank_items", op.f("ix_question_bank_items_node_role"))
    _drop_column_if_exists("question_bank_items", "material_text")
    _drop_column_if_exists("question_bank_items", "group_stem")
    _drop_column_if_exists("question_bank_items", "node_role")
    _drop_column_if_exists("question_bank_items", "parent_question_id")

    _drop_foreign_key_if_exists("paper_review_questions", "fk_paper_review_questions_parent_question_id")
    _drop_index_if_exists("paper_review_questions", op.f("ix_paper_review_questions_parent_question_id"))
    _drop_column_if_exists("paper_review_questions", "material_text")
    _drop_column_if_exists("paper_review_questions", "group_stem")
    _drop_column_if_exists("paper_review_questions", "node_role")
    _drop_column_if_exists("paper_review_questions", "parent_question_id")


def _table_has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if _table_has_column(table_name, str(column.name)):
        return
    op.add_column(table_name, column)


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    if not _table_has_column(table_name, column_name):
        return
    op.drop_column(table_name, column_name)


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str]) -> None:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return
    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name in existing_indexes:
        return
    op.create_index(index_name, table_name, columns, unique=False)


def _drop_index_if_exists(table_name: str, index_name: str) -> None:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return
    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name not in existing_indexes:
        return
    op.drop_index(index_name, table_name=table_name)


def _create_foreign_key_if_missing(
    source_table: str,
    constraint_name: str,
    referent_table: str,
    local_cols: list[str],
    remote_cols: list[str],
    *,
    ondelete: str | None = None,
) -> None:
    inspector = sa.inspect(op.get_bind())
    if source_table not in inspector.get_table_names():
        return
    existing = {item["name"] for item in inspector.get_foreign_keys(source_table)}
    if constraint_name in existing:
        return
    op.create_foreign_key(
        constraint_name,
        source_table,
        referent_table,
        local_cols,
        remote_cols,
        ondelete=ondelete,
    )


def _drop_foreign_key_if_exists(table_name: str, constraint_name: str) -> None:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return
    existing = {item["name"] for item in inspector.get_foreign_keys(table_name)}
    if constraint_name not in existing:
        return
    op.drop_constraint(constraint_name, table_name, type_="foreignkey")
