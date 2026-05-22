"""expand generation job and background task columns to longtext

Revision ID: 1a2b3c4d5e6f
Revises: 0f1e2d3c4b5a
Create Date: 2026-05-11 18:35:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "1a2b3c4d5e6f"
down_revision = "0f1e2d3c4b5a"
branch_labels = None
depends_on = None


LONGTEXT = sa.Text().with_variant(mysql.LONGTEXT(), "mysql")
TEXT = sa.Text()


def _alter_text_column_if_exists(
    inspector: sa.Inspector,
    table_name: str,
    column_name: str,
    *,
    nullable: bool,
    target_type: sa.types.TypeEngine,
    existing_type: sa.types.TypeEngine | None = None,
) -> None:
    if table_name not in inspector.get_table_names():
        return
    columns = {column["name"]: column for column in inspector.get_columns(table_name)}
    if column_name not in columns:
        return
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.alter_column(
            column_name,
            existing_type=existing_type or TEXT,
            type_=target_type,
            existing_nullable=nullable,
        )


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for column_name, nullable in (
        ("context", False),
        ("result", True),
        ("review", True),
        ("error", True),
    ):
        _alter_text_column_if_exists(
            inspector,
            "generation_jobs",
            column_name,
            nullable=nullable,
            target_type=LONGTEXT,
        )

    for column_name, nullable in (
        ("payload", False),
        ("last_error", True),
    ):
        _alter_text_column_if_exists(
            inspector,
            "background_tasks",
            column_name,
            nullable=nullable,
            target_type=LONGTEXT,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for column_name, nullable in (
        ("context", False),
        ("result", True),
        ("review", True),
        ("error", True),
    ):
        _alter_text_column_if_exists(
            inspector,
            "generation_jobs",
            column_name,
            nullable=nullable,
            target_type=TEXT,
            existing_type=LONGTEXT,
        )

    for column_name, nullable in (
        ("payload", False),
        ("last_error", True),
    ):
        _alter_text_column_if_exists(
            inspector,
            "background_tasks",
            column_name,
            nullable=nullable,
            target_type=TEXT,
            existing_type=LONGTEXT,
        )
