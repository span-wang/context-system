"""add review_note to exam_questions

Revision ID: 5f6c7a8b9d10
Revises: 7987b9d25a7f
Create Date: 2026-05-06 14:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5f6c7a8b9d10"
down_revision = "7987b9d25a7f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exam_questions", sa.Column("review_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("exam_questions", "review_note")
