"""remove auto training jobs and audit logs

Revision ID: 2b3c4d5e6f7
Revises: 1a2b3c4d5e6f
Create Date: 2026-05-11 19:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "2b3c4d5e6f7"
down_revision = "1a2b3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "analysis_jobs" in existing_tables:
        op.execute(
            sa.text(
                """
                DELETE FROM analysis_jobs
                WHERE job_type = :job_type OR scope_type = :scope_type
                """
            ).bindparams(job_type="auto_training", scope_type="auto_training")
        )

    if "audit_logs" in existing_tables:
        op.execute(
            sa.text(
                """
                DELETE FROM audit_logs
                WHERE module = :module
                """
            ).bindparams(module="auto_training")
        )


def downgrade() -> None:
    pass
