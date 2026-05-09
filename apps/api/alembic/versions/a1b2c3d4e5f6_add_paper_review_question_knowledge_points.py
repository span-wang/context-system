"""add paper review question knowledge points

Revision ID: a1b2c3d4e5f6
Revises: d9e0f1a2b3c4
Create Date: 2026-05-09 18:20:00.000000
"""

from __future__ import annotations

import hashlib

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from sqlalchemy.engine import Connection


revision = "a1b2c3d4e5f6"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    long_text = sa.Text().with_variant(mysql.LONGTEXT(), "mysql")
    bind = op.get_bind()

    if not _column_exists(bind, "paper_review_questions", "content_fingerprint"):
        op.add_column(
            "paper_review_questions",
            sa.Column("content_fingerprint", sa.String(length=64), nullable=True),
        )
    if not _index_exists(bind, "paper_review_questions", op.f("ix_paper_review_questions_content_fingerprint")):
        op.create_index(
            op.f("ix_paper_review_questions_content_fingerprint"),
            "paper_review_questions",
            ["content_fingerprint"],
            unique=False,
        )

    if not _table_exists(bind, "paper_review_question_knowledge_points"):
        op.create_table(
            "paper_review_question_knowledge_points",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("question_id", sa.Integer(), nullable=False),
            sa.Column("knowledge_point_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("relation_type", sa.String(length=32), nullable=False),
            sa.Column("source", sa.String(length=32), nullable=False),
            sa.Column("confidence", sa.Numeric(precision=5, scale=2), nullable=True),
            sa.Column("reason", long_text, nullable=True),
            sa.Column("rank", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["knowledge_point_id"], ["knowledge_points.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["question_id"], ["paper_review_questions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("question_id", "knowledge_point_id", name="uq_prq_kp_question_point"),
        )
    if not _index_exists(bind, "paper_review_question_knowledge_points", op.f("ix_paper_review_question_knowledge_points_question_id")):
        op.create_index(
            op.f("ix_paper_review_question_knowledge_points_question_id"),
            "paper_review_question_knowledge_points",
            ["question_id"],
            unique=False,
        )
    if not _index_exists(bind, "paper_review_question_knowledge_points", op.f("ix_paper_review_question_knowledge_points_knowledge_point_id")):
        op.create_index(
            op.f("ix_paper_review_question_knowledge_points_knowledge_point_id"),
            "paper_review_question_knowledge_points",
            ["knowledge_point_id"],
            unique=False,
        )
    if not _index_exists(bind, "paper_review_question_knowledge_points", op.f("ix_paper_review_question_knowledge_points_tenant_id")):
        op.create_index(
            op.f("ix_paper_review_question_knowledge_points_tenant_id"),
            "paper_review_question_knowledge_points",
            ["tenant_id"],
            unique=False,
        )

    rows = bind.execute(
        sa.text(
            """
            SELECT id, section_id, question_no, source_raw_text
            FROM paper_review_questions
            WHERE content_fingerprint IS NULL
            """
        )
    ).mappings()
    for row in rows:
        normalized = "|".join(
            [
                str(row["section_id"] or 0),
                str(row["question_no"] or "").strip(),
                " ".join(str(row["source_raw_text"] or "").replace("\r\n", "\n").replace("\r", "\n").lower().split())[:2000],
            ]
        )
        fingerprint = hashlib.sha1(normalized.encode("utf-8")).hexdigest()
        bind.execute(
            sa.text(
                """
                UPDATE paper_review_questions
                SET content_fingerprint = :fingerprint
                WHERE id = :row_id
                """
            ),
            {"fingerprint": fingerprint, "row_id": row["id"]},
        )
    op.alter_column(
        "paper_review_questions",
        "content_fingerprint",
        existing_type=sa.String(length=64),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_paper_review_question_knowledge_points_tenant_id"),
        table_name="paper_review_question_knowledge_points",
    )
    op.drop_index(
        op.f("ix_paper_review_question_knowledge_points_knowledge_point_id"),
        table_name="paper_review_question_knowledge_points",
    )
    op.drop_index(
        op.f("ix_paper_review_question_knowledge_points_question_id"),
        table_name="paper_review_question_knowledge_points",
    )
    op.drop_table("paper_review_question_knowledge_points")
    op.drop_index(op.f("ix_paper_review_questions_content_fingerprint"), table_name="paper_review_questions")
    op.drop_column("paper_review_questions", "content_fingerprint")


def _table_exists(bind: Connection, table_name: str) -> bool:
    return bool(bind.execute(sa.text("SHOW TABLES LIKE :table_name"), {"table_name": table_name}).fetchone())


def _column_exists(bind: Connection, table_name: str, column_name: str) -> bool:
    return bool(
        bind.execute(
            sa.text(f"SHOW COLUMNS FROM `{table_name}` LIKE :column_name"),
            {"column_name": column_name},
        ).fetchone()
    )


def _index_exists(bind: Connection, table_name: str, index_name: str) -> bool:
    return bool(
        bind.execute(
            sa.text(f"SHOW INDEX FROM `{table_name}` WHERE Key_name = :index_name"),
            {"index_name": index_name},
        ).fetchone()
    )
