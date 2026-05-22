"""add mastery snapshots

Revision ID: 5e6f7a8b9c0d
Revises: 4d5e6f7a8b9c
Create Date: 2026-05-14 14:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "5e6f7a8b9c0d"
down_revision = "4d5e6f7a8b9c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _rename_table_if_incompatible(
        "mastery_snapshots",
        {"user_id", "subject_id", "knowledge_point_id", "snapshot_date", "tenant_id"},
    )

    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())

    if "mastery_snapshots" not in existing_tables:
        op.create_table(
            "mastery_snapshots",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("subject_id", sa.Integer(), nullable=False),
            sa.Column("knowledge_point_id", sa.Integer(), nullable=False),
            sa.Column("mastery_score", sa.Numeric(precision=5, scale=2), nullable=False),
            sa.Column("answered_count", sa.Integer(), nullable=False),
            sa.Column("correct_count", sa.Integer(), nullable=False),
            sa.Column("snapshot_date", sa.Date(), nullable=False),
            sa.Column("last_practiced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["knowledge_point_id"], ["knowledge_points.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "knowledge_point_id", name="uq_mastery_snapshots_user_kp"),
        )

    _create_index_if_missing("mastery_snapshots", op.f("ix_mastery_snapshots_user_id"), ["user_id"])
    _create_index_if_missing("mastery_snapshots", op.f("ix_mastery_snapshots_subject_id"), ["subject_id"])
    _create_index_if_missing("mastery_snapshots", op.f("ix_mastery_snapshots_knowledge_point_id"), ["knowledge_point_id"])
    _create_index_if_missing("mastery_snapshots", op.f("ix_mastery_snapshots_tenant_id"), ["tenant_id"])
    _create_unique_constraint_if_missing(
        "mastery_snapshots",
        "uq_mastery_snapshots_user_kp",
        ["user_id", "knowledge_point_id"],
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "mastery_snapshots" in inspector.get_table_names():
        op.drop_table("mastery_snapshots")


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


def _create_unique_constraint_if_missing(table_name: str, constraint_name: str, columns: list[str]) -> None:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    if not set(columns).issubset(existing_columns):
        return
    existing_constraints = {item["name"] for item in inspector.get_unique_constraints(table_name) if item.get("name")}
    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name) if index.get("unique")}
    if constraint_name in existing_constraints or constraint_name in existing_indexes:
        return
    op.create_unique_constraint(constraint_name, table_name, columns)


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
