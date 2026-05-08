"""add library parse result history

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-07 13:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())
    if "library_parse_results" in existing_tables:
        return

    op.create_table(
        "library_parse_results",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("file_id", sa.String(length=64), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("parsed_text", sa.Text(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=True),
        sa.Column("parse_options", sa.Text(), nullable=False),
        sa.Column("warnings", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_library_parse_results_created_at"), "library_parse_results", ["created_at"], unique=False)
    op.create_index(op.f("ix_library_parse_results_file_id"), "library_parse_results", ["file_id"], unique=False)
    op.create_index(op.f("ix_library_parse_results_sequence_number"), "library_parse_results", ["sequence_number"], unique=False)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())
    if "library_parse_results" not in existing_tables:
        return

    existing_indexes = {index["name"] for index in inspector.get_indexes("library_parse_results")}
    for index_name in (
        op.f("ix_library_parse_results_sequence_number"),
        op.f("ix_library_parse_results_file_id"),
        op.f("ix_library_parse_results_created_at"),
    ):
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name="library_parse_results")
    op.drop_table("library_parse_results")
