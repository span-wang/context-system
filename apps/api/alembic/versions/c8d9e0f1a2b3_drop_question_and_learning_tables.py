"""drop question and learning tables

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-05-09 12:30:00
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "c8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("favorites")
    op.drop_table("wrong_book_items")
    op.drop_table("practice_answers")
    op.drop_table("mock_exam_questions")
    op.drop_table("practice_set_questions")
    op.drop_table("question_source_links")
    op.drop_table("question_knowledge_links")
    op.drop_table("question_bank_items")
    op.drop_table("exam_questions")


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for the removed question and learning tables.")
