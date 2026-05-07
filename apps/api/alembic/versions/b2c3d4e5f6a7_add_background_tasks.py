"""add background tasks

Revision ID: b2c3d4e5f6a7
Revises: 9a0b1c2d3e4f
Create Date: 2026-05-06 19:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "b2c3d4e5f6a7"
down_revision = "9a0b1c2d3e4f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "background_tasks" in existing_tables:
        return

    op.create_table(
        "background_tasks",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_background_tasks_created_at"), "background_tasks", ["created_at"], unique=False)
    op.create_index(op.f("ix_background_tasks_next_run_at"), "background_tasks", ["next_run_at"], unique=False)
    op.create_index(op.f("ix_background_tasks_status"), "background_tasks", ["status"], unique=False)
    op.create_index(op.f("ix_background_tasks_task_type"), "background_tasks", ["task_type"], unique=False)
    op.create_index(op.f("ix_background_tasks_worker_id"), "background_tasks", ["worker_id"], unique=False)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())
    if "background_tasks" not in existing_tables:
        return

    for index_name in (
        op.f("ix_background_tasks_worker_id"),
        op.f("ix_background_tasks_task_type"),
        op.f("ix_background_tasks_status"),
        op.f("ix_background_tasks_next_run_at"),
        op.f("ix_background_tasks_created_at"),
    ):
        if index_name in {index["name"] for index in inspector.get_indexes("background_tasks")}:
            op.drop_index(index_name, table_name="background_tasks")
    op.drop_table("background_tasks")
