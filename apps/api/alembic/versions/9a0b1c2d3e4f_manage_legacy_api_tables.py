"""manage legacy api tables with alembic

Revision ID: 9a0b1c2d3e4f
Revises: 5f6c7a8b9d10
Create Date: 2026-05-06 17:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "9a0b1c2d3e4f"
down_revision = "5f6c7a8b9d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())

    if "library_files" not in existing_tables:
        op.create_table(
            "library_files",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("sha256", sa.String(length=128), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("size", sa.Integer(), nullable=False),
            sa.Column("mime", sa.String(length=128), nullable=False),
            sa.Column("storage_path", sa.String(length=255), nullable=False),
            sa.Column("subject", sa.String(length=128), nullable=False),
            sa.Column("category", sa.String(length=128), nullable=True),
            sa.Column("chapter", sa.String(length=255), nullable=True),
            sa.Column("source_type", sa.String(length=32), nullable=False),
            sa.Column("source_authority", sa.String(length=32), nullable=False),
            sa.Column("source_title", sa.String(length=255), nullable=False),
            sa.Column("source_publisher", sa.String(length=255), nullable=True),
            sa.Column("source_code", sa.String(length=128), nullable=True),
            sa.Column("source_version", sa.String(length=128), nullable=True),
            sa.Column("year", sa.Integer(), nullable=True),
            sa.Column("tags", sa.Text(), nullable=False),
            sa.Column("parsed_text", sa.Text(), nullable=True),
            sa.Column("token_count", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_library_files_sha256"), "library_files", ["sha256"], unique=True)
        op.create_index(op.f("ix_library_files_subject"), "library_files", ["subject"], unique=False)

    if "generation_jobs" not in existing_tables:
        op.create_table(
            "generation_jobs",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("context", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("result", sa.Text(), nullable=True),
            sa.Column("review", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_generation_jobs_created_at"), "generation_jobs", ["created_at"], unique=False)
        op.create_index(op.f("ix_generation_jobs_status"), "generation_jobs", ["status"], unique=False)

    if "background_tasks" not in existing_tables:
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

    if "workflow_topics" not in existing_tables:
        op.create_table(
            "workflow_topics",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("brief", sa.Text(), nullable=True),
            sa.Column("subject", sa.String(length=128), nullable=False),
            sa.Column("category", sa.String(length=128), nullable=True),
            sa.Column("chapter", sa.String(length=255), nullable=True),
            sa.Column("content_type", sa.String(length=64), nullable=False),
            sa.Column("owner", sa.String(length=128), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("review_status", sa.String(length=32), nullable=False),
            sa.Column("priority", sa.String(length=32), nullable=False),
            sa.Column("scheduled_date", sa.Date(), nullable=True),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("publish_channel", sa.String(length=64), nullable=False),
            sa.Column("content_goal", sa.Text(), nullable=True),
            sa.Column("audience", sa.String(length=255), nullable=True),
            sa.Column("material_file_ids", sa.Text(), nullable=False),
            sa.Column("ragflow_dataset_ids", sa.Text(), nullable=False),
            sa.Column("generation_job_id", sa.String(length=64), nullable=True),
            sa.Column("confirmed_by", sa.String(length=128), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_workflow_topics_scheduled_date"), "workflow_topics", ["scheduled_date"], unique=False)
        op.create_index(op.f("ix_workflow_topics_status"), "workflow_topics", ["status"], unique=False)
        op.create_index(op.f("ix_workflow_topics_updated_at"), "workflow_topics", ["updated_at"], unique=False)

    if "workflow_events" not in existing_tables:
        op.create_table(
            "workflow_events",
            sa.Column("id", sa.String(length=96), nullable=False),
            sa.Column("topic_id", sa.String(length=64), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("actor", sa.String(length=128), nullable=True),
            sa.Column("snapshot", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_workflow_events_topic_id"), "workflow_events", ["topic_id"], unique=False)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())

    if "workflow_events" in existing_tables:
        _drop_index_if_exists(inspector, "workflow_events", op.f("ix_workflow_events_topic_id"))
        op.drop_table("workflow_events")
    if "workflow_topics" in existing_tables:
        _drop_index_if_exists(inspector, "workflow_topics", op.f("ix_workflow_topics_updated_at"))
        _drop_index_if_exists(inspector, "workflow_topics", op.f("ix_workflow_topics_status"))
        _drop_index_if_exists(inspector, "workflow_topics", op.f("ix_workflow_topics_scheduled_date"))
        op.drop_table("workflow_topics")
    if "generation_jobs" in existing_tables:
        _drop_index_if_exists(inspector, "generation_jobs", op.f("ix_generation_jobs_status"))
        _drop_index_if_exists(inspector, "generation_jobs", op.f("ix_generation_jobs_created_at"))
        op.drop_table("generation_jobs")
    if "background_tasks" in existing_tables:
        _drop_index_if_exists(inspector, "background_tasks", op.f("ix_background_tasks_worker_id"))
        _drop_index_if_exists(inspector, "background_tasks", op.f("ix_background_tasks_task_type"))
        _drop_index_if_exists(inspector, "background_tasks", op.f("ix_background_tasks_status"))
        _drop_index_if_exists(inspector, "background_tasks", op.f("ix_background_tasks_next_run_at"))
        _drop_index_if_exists(inspector, "background_tasks", op.f("ix_background_tasks_created_at"))
        op.drop_table("background_tasks")
    if "library_files" in existing_tables:
        _drop_index_if_exists(inspector, "library_files", op.f("ix_library_files_subject"))
        _drop_index_if_exists(inspector, "library_files", op.f("ix_library_files_sha256"))
        op.drop_table("library_files")


def _drop_index_if_exists(inspector, table_name: str, index_name: str) -> None:
    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name in existing_indexes:
        op.drop_index(index_name, table_name=table_name)
