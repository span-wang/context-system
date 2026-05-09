"""expand target_id columns for migrated audit data

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-09 00:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())

    if "review_tasks" in existing_tables:
        with op.batch_alter_table("review_tasks") as batch_op:
            batch_op.alter_column(
                "target_id",
                existing_type=sa.String(length=64),
                type_=sa.String(length=255),
                existing_nullable=False,
            )

    if "audit_logs" in existing_tables:
        with op.batch_alter_table("audit_logs") as batch_op:
            batch_op.alter_column(
                "target_id",
                existing_type=sa.String(length=64),
                type_=sa.Text(),
                existing_nullable=True,
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())

    if "review_tasks" in existing_tables:
        with op.batch_alter_table("review_tasks") as batch_op:
            batch_op.alter_column(
                "target_id",
                existing_type=sa.String(length=255),
                type_=sa.String(length=64),
                existing_nullable=False,
            )

    if "audit_logs" in existing_tables:
        with op.batch_alter_table("audit_logs") as batch_op:
            batch_op.alter_column(
                "target_id",
                existing_type=sa.Text(),
                type_=sa.String(length=64),
                existing_nullable=True,
            )
