"""expand parsed text columns to longtext for mysql

Revision ID: b7c8d9e0f1a2
Revises: a7b8c9d0e1f2
Create Date: 2026-05-09 10:05:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "b7c8d9e0f1a2"
down_revision = "a7b8c9d0e1f2"
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
    _alter_text_column_if_exists(
        inspector,
        "assets",
        "parsed_text",
        nullable=True,
        target_type=LONGTEXT,
    )
    _alter_text_column_if_exists(
        inspector,
        "library_files",
        "parsed_text",
        nullable=True,
        target_type=LONGTEXT,
    )
    _alter_text_column_if_exists(
        inspector,
        "library_parse_results",
        "parsed_text",
        nullable=False,
        target_type=LONGTEXT,
    )
    _alter_text_column_if_exists(
        inspector,
        "library_parse_results",
        "markdown",
        nullable=True,
        target_type=LONGTEXT,
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    _alter_text_column_if_exists(
        inspector,
        "assets",
        "parsed_text",
        nullable=True,
        target_type=TEXT,
        existing_type=LONGTEXT,
    )
    _alter_text_column_if_exists(
        inspector,
        "library_files",
        "parsed_text",
        nullable=True,
        target_type=TEXT,
        existing_type=LONGTEXT,
    )
    _alter_text_column_if_exists(
        inspector,
        "library_parse_results",
        "parsed_text",
        nullable=False,
        target_type=TEXT,
        existing_type=LONGTEXT,
    )
    _alter_text_column_if_exists(
        inspector,
        "library_parse_results",
        "markdown",
        nullable=True,
        target_type=TEXT,
        existing_type=LONGTEXT,
    )
