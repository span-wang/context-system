"""bind chapters to categories

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-07 22:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "chapters" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("chapters")}
    if "category_id" not in columns:
        with op.batch_alter_table("chapters") as batch_op:
            batch_op.add_column(sa.Column("category_id", sa.Integer(), nullable=True))
            batch_op.create_index(op.f("ix_chapters_category_id"), ["category_id"], unique=False)
            batch_op.create_foreign_key(
                "fk_chapters_category_id_subject_categories",
                "subject_categories",
                ["category_id"],
                ["id"],
            )
        inspector = sa.inspect(bind)

    chapter_columns = {column["name"] for column in inspector.get_columns("chapters")}
    if "category_id" not in chapter_columns:
        return

    chapter_table = sa.table(
        "chapters",
        sa.column("id", sa.Integer()),
        sa.column("subject_id", sa.Integer()),
        sa.column("category_id", sa.Integer()),
        sa.column("parent_id", sa.Integer()),
        sa.column("sort_order", sa.Integer()),
    )
    point_table = sa.table(
        "knowledge_points",
        sa.column("id", sa.Integer()),
        sa.column("chapter_id", sa.Integer()),
        sa.column("category_id", sa.Integer()),
    )
    category_table = sa.table(
        "subject_categories",
        sa.column("id", sa.Integer()),
        sa.column("subject_id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("sort_order", sa.Integer()),
    )

    category_rows = bind.execute(
        sa.select(category_table.c.id, category_table.c.subject_id, category_table.c.name, category_table.c.sort_order)
    ).fetchall()
    default_category_by_subject: dict[int, int] = {}
    categories_by_subject: dict[int, list[tuple[int, str, int | None]]] = {}
    for category_id, subject_id, name, sort_order in category_rows:
        categories_by_subject.setdefault(int(subject_id), []).append((int(category_id), str(name or ""), sort_order))

    for subject_id, items in categories_by_subject.items():
        ranked = sorted(items, key=lambda row: ((row[2] or 0), row[0]))
        preferred = next((category_id for category_id, name, _ in ranked if "实务" in name), None)
        default_category_by_subject[subject_id] = preferred or ranked[0][0]

    chapter_rows = bind.execute(
        sa.select(
            chapter_table.c.id,
            chapter_table.c.subject_id,
            chapter_table.c.category_id,
            chapter_table.c.parent_id,
        )
    ).fetchall()
    chapter_by_id = {
        int(chapter_id): {
            "subject_id": int(subject_id),
            "category_id": int(category_id) if category_id is not None else None,
            "parent_id": int(parent_id) if parent_id is not None else None,
        }
        for chapter_id, subject_id, category_id, parent_id in chapter_rows
    }

    root_updates: list[dict[str, int]] = []
    for chapter_id, data in chapter_by_id.items():
        if data["category_id"] is not None:
            continue
        if data["parent_id"] is not None:
            continue
        category_id = default_category_by_subject.get(data["subject_id"])
        if category_id is None:
            continue
        data["category_id"] = category_id
        root_updates.append({"chapter_id": chapter_id, "category_id": category_id})

    for item in root_updates:
        bind.execute(
            chapter_table.update()
            .where(chapter_table.c.id == item["chapter_id"])
            .values(category_id=item["category_id"])
        )

    pending = True
    while pending:
        pending = False
        for chapter_id, data in chapter_by_id.items():
            if data["category_id"] is not None:
                continue
            parent_id = data["parent_id"]
            if parent_id is None:
                continue
            parent = chapter_by_id.get(parent_id)
            if parent is None or parent["category_id"] is None:
                continue
            data["category_id"] = parent["category_id"]
            bind.execute(
                chapter_table.update()
                .where(chapter_table.c.id == chapter_id)
                .values(category_id=parent["category_id"])
            )
            pending = True

    for chapter_id, data in chapter_by_id.items():
        if data["category_id"] is None:
            continue
        bind.execute(
            point_table.update()
            .where(point_table.c.chapter_id == chapter_id)
            .where(point_table.c.category_id.is_(None))
            .values(category_id=data["category_id"])
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "chapters" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("chapters")}
    if "category_id" not in columns:
        return

    foreign_key_names = [
        foreign_key["name"]
        for foreign_key in inspector.get_foreign_keys("chapters")
        if foreign_key.get("constrained_columns") == ["category_id"] and foreign_key.get("name")
    ]
    index_names = {
        index["name"]
        for index in inspector.get_indexes("chapters")
        if index.get("column_names") == ["category_id"]
    }

    with op.batch_alter_table("chapters") as batch_op:
        for foreign_key_name in foreign_key_names:
            batch_op.drop_constraint(foreign_key_name, type_="foreignkey")
        if op.f("ix_chapters_category_id") in index_names:
            batch_op.drop_index(op.f("ix_chapters_category_id"))
        batch_op.drop_column("category_id")
