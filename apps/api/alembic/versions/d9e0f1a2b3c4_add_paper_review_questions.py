"""add paper review questions

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-05-09 14:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    long_text = sa.Text().with_variant(mysql.LONGTEXT(), "mysql")
    op.create_table(
        "paper_review_questions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("paper_id", sa.Integer(), nullable=False),
        sa.Column("section_id", sa.Integer(), nullable=True),
        sa.Column("question_uid", sa.String(length=64), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("question_no", sa.String(length=32), nullable=False),
        sa.Column("question_type", sa.String(length=64), nullable=False),
        sa.Column("source_section_name", sa.String(length=128), nullable=False),
        sa.Column("source_raw_text", long_text, nullable=False),
        sa.Column("stem_text", long_text, nullable=False),
        sa.Column("options_json", sa.JSON(), nullable=True),
        sa.Column("answer_text", long_text, nullable=True),
        sa.Column("analysis_text", long_text, nullable=True),
        sa.Column("difficulty_level", sa.Integer(), nullable=True),
        sa.Column("quality_score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("subquestion_count", sa.Integer(), nullable=False),
        sa.Column("quality_issues_json", sa.JSON(), nullable=True),
        sa.Column("parse_status", sa.String(length=32), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("review_note", long_text, nullable=True),
        sa.Column("ai_review_status", sa.String(length=32), nullable=True),
        sa.Column("ai_review_note", long_text, nullable=True),
        sa.Column("ai_standardization_note", long_text, nullable=True),
        sa.Column("last_ai_standardized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ai_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["paper_id"], ["exam_papers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["section_id"], ["paper_sections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_paper_review_questions_paper_id"), "paper_review_questions", ["paper_id"], unique=False)
    op.create_index(op.f("ix_paper_review_questions_question_uid"), "paper_review_questions", ["question_uid"], unique=True)
    op.create_index(op.f("ix_paper_review_questions_review_status"), "paper_review_questions", ["review_status"], unique=False)
    op.create_index(op.f("ix_paper_review_questions_section_id"), "paper_review_questions", ["section_id"], unique=False)
    op.create_index(op.f("ix_paper_review_questions_tenant_id"), "paper_review_questions", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_table("paper_review_questions")
