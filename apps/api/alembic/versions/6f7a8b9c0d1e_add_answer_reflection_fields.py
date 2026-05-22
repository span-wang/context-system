"""add answer reflection fields

Revision ID: 6f7a8b9c0d1e
Revises: 5e6f7a8b9c0d
Create Date: 2026-05-14 15:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "6f7a8b9c0d1e"
down_revision = "5e6f7a8b9c0d"
branch_labels = None
depends_on = None


LONGTEXT = sa.Text().with_variant(mysql.LONGTEXT(), "mysql")


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "practice_answers" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("practice_answers")}
    if "wrong_reason_tags_json" not in columns:
        op.add_column("practice_answers", sa.Column("wrong_reason_tags_json", sa.JSON(), nullable=True))
    if "reflection_note" not in columns:
        op.add_column("practice_answers", sa.Column("reflection_note", LONGTEXT, nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "practice_answers" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("practice_answers")}
    if "reflection_note" in columns:
        op.drop_column("practice_answers", "reflection_note")
    if "wrong_reason_tags_json" in columns:
        op.drop_column("practice_answers", "wrong_reason_tags_json")
