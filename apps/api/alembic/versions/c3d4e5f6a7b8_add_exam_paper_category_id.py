"""add category_id to exam_papers

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-06 20:25:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "exam_papers" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("exam_papers")}
    if "category_id" in columns:
        return

    with op.batch_alter_table("exam_papers") as batch_op:
        batch_op.add_column(sa.Column("category_id", sa.Integer(), nullable=True))
        batch_op.create_index(op.f("ix_exam_papers_category_id"), ["category_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_exam_papers_category_id_subject_categories",
            "subject_categories",
            ["category_id"],
            ["id"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "exam_papers" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("exam_papers")}
    if "category_id" not in columns:
        return

    foreign_key_names = [
        foreign_key["name"]
        for foreign_key in inspector.get_foreign_keys("exam_papers")
        if foreign_key.get("constrained_columns") == ["category_id"] and foreign_key.get("name")
    ]
    index_names = {
        index["name"]
        for index in inspector.get_indexes("exam_papers")
        if index.get("column_names") == ["category_id"]
    }

    with op.batch_alter_table("exam_papers") as batch_op:
        for foreign_key_name in foreign_key_names:
            batch_op.drop_constraint(foreign_key_name, type_="foreignkey")
        if op.f("ix_exam_papers_category_id") in index_names:
            batch_op.drop_index(op.f("ix_exam_papers_category_id"))
        batch_op.drop_column("category_id")
