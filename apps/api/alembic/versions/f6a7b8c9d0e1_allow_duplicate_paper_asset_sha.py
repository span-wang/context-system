"""allow duplicate paper asset sha values

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-08 23:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "assets" not in inspector.get_table_names():
        return

    index_names = {index["name"]: bool(index.get("unique")) for index in inspector.get_indexes("assets")}
    unique_sha_index_name = next(
        (
            name
            for name, is_unique in index_names.items()
            if is_unique and name == op.f("ix_assets_sha256")
        ),
        None,
    )
    if unique_sha_index_name is not None:
        with op.batch_alter_table("assets") as batch_op:
            batch_op.drop_index(unique_sha_index_name)
            batch_op.create_index(op.f("ix_assets_sha256"), ["sha256"], unique=False)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "assets" not in inspector.get_table_names():
        return

    index_names = {index["name"]: bool(index.get("unique")) for index in inspector.get_indexes("assets")}
    if index_names.get(op.f("ix_assets_sha256")) is False:
        with op.batch_alter_table("assets") as batch_op:
            batch_op.drop_index(op.f("ix_assets_sha256"))
            batch_op.create_index(op.f("ix_assets_sha256"), ["sha256"], unique=True)
