"""add question bank tables

Revision ID: 0f1e2d3c4b5a
Revises: a1b2c3d4e5f6
Create Date: 2026-05-09 20:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0f1e2d3c4b5a"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    long_text = sa.Text().with_variant(mysql.LONGTEXT(), "mysql")

    if "question_bank_items" not in existing_tables:
        op.create_table(
            "question_bank_items",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("subject_id", sa.Integer(), nullable=True),
            sa.Column("category_id", sa.Integer(), nullable=True),
            sa.Column("question_uid", sa.String(length=64), nullable=False),
            sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
            sa.Column("question_type", sa.String(length=64), nullable=False),
            sa.Column("stem_text", long_text, nullable=False),
            sa.Column("options_json", sa.JSON(), nullable=True),
            sa.Column("answer_text", long_text, nullable=True),
            sa.Column("analysis_text", long_text, nullable=True),
            sa.Column("difficulty_level", sa.Integer(), nullable=True),
            sa.Column("quality_score", sa.Numeric(precision=5, scale=2), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("source_count", sa.Integer(), nullable=False),
            sa.Column("first_source_question_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["category_id"], ["subject_categories.id"]),
            sa.ForeignKeyConstraint(["first_source_question_id"], ["paper_review_questions.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    _create_index_if_missing("question_bank_items", op.f("ix_question_bank_items_category_id"), ["category_id"])
    _create_index_if_missing("question_bank_items", op.f("ix_question_bank_items_content_fingerprint"), ["content_fingerprint"], unique=True)
    _create_index_if_missing("question_bank_items", op.f("ix_question_bank_items_first_source_question_id"), ["first_source_question_id"])
    _create_index_if_missing("question_bank_items", op.f("ix_question_bank_items_question_type"), ["question_type"])
    _create_index_if_missing("question_bank_items", op.f("ix_question_bank_items_question_uid"), ["question_uid"], unique=True)
    _create_index_if_missing("question_bank_items", op.f("ix_question_bank_items_status"), ["status"])
    _create_index_if_missing("question_bank_items", op.f("ix_question_bank_items_subject_id"), ["subject_id"])
    _create_index_if_missing("question_bank_items", op.f("ix_question_bank_items_tenant_id"), ["tenant_id"])

    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "question_bank_source_links" not in existing_tables:
        op.create_table(
            "question_bank_source_links",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("bank_question_id", sa.Integer(), nullable=False),
            sa.Column("source_type", sa.String(length=64), nullable=False),
            sa.Column("source_question_id", sa.Integer(), nullable=False),
            sa.Column("paper_id", sa.Integer(), nullable=True),
            sa.Column("section_id", sa.Integer(), nullable=True),
            sa.Column("question_no", sa.String(length=32), nullable=True),
            sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["bank_question_id"], ["question_bank_items.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["paper_id"], ["exam_papers.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["section_id"], ["paper_sections.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["source_question_id"], ["paper_review_questions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("source_type", "source_question_id", name="uq_qb_source_link_source"),
        )

    _create_index_if_missing("question_bank_source_links", op.f("ix_question_bank_source_links_bank_question_id"), ["bank_question_id"])
    _create_index_if_missing("question_bank_source_links", op.f("ix_question_bank_source_links_paper_id"), ["paper_id"])
    _create_index_if_missing("question_bank_source_links", op.f("ix_question_bank_source_links_source_fingerprint"), ["source_fingerprint"])
    _create_index_if_missing("question_bank_source_links", op.f("ix_question_bank_source_links_source_question_id"), ["source_question_id"])
    _create_index_if_missing("question_bank_source_links", op.f("ix_question_bank_source_links_source_type"), ["source_type"])
    _create_index_if_missing("question_bank_source_links", op.f("ix_question_bank_source_links_status"), ["status"])
    _create_index_if_missing("question_bank_source_links", op.f("ix_question_bank_source_links_tenant_id"), ["tenant_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())
    if "question_bank_source_links" in existing_tables:
        op.drop_table("question_bank_source_links")
    if "question_bank_items" in existing_tables:
        op.drop_table("question_bank_items")


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str], *, unique: bool = False) -> None:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return
    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name in existing_indexes:
        return
    op.create_index(index_name, table_name, columns, unique=unique)
