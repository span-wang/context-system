from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, or_, select, update

from app.db.session import SessionLocal
from app.models.legacy import (
    LegacyBackgroundTask,
    LegacyGenerationJob,
    LegacyLibraryFile,
    LegacyWorkflowEvent,
    LegacyWorkflowTopic,
)
from schemas.generation import GenerationJob
from schemas.library import LibraryFile, LibraryFilePatch
from schemas.workflow import WorkflowEvent, WorkflowTopic, WorkflowTopicPatch


class Database:
    """Compatibility repository for the original APIs.

    The old implementation opened its own sqlite3 connections and created its
    own schema. This class keeps the public method surface, but all data access
    now goes through the shared SQLAlchemy SessionLocal/engine configured by
    app.db.session.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path

    def init_schema(self) -> None:
        return None

    def insert_library_file(self, file: LibraryFile) -> LibraryFile:
        with SessionLocal() as session:
            session.add(self._library_to_model(file))
            session.commit()
        return file

    def get_library_by_sha(self, sha256: str) -> LibraryFile | None:
        with SessionLocal() as session:
            row = session.scalar(select(LegacyLibraryFile).where(LegacyLibraryFile.sha256 == sha256))
            return self._library_from_model(row) if row else None

    def get_library_file(self, file_id: str) -> LibraryFile | None:
        with SessionLocal() as session:
            row = session.get(LegacyLibraryFile, file_id)
            return self._library_from_model(row) if row else None

    def list_library_files(
        self,
        subject: str | None = None,
        category: str | None = None,
        source_type: str | None = None,
        search: str | None = None,
    ) -> list[LibraryFile]:
        statement = select(LegacyLibraryFile)
        if subject:
            statement = statement.where(LegacyLibraryFile.subject == subject)
        if category:
            statement = statement.where(LegacyLibraryFile.category == category)
        if source_type:
            statement = statement.where(LegacyLibraryFile.source_type == source_type)
        if search:
            pattern = f"%{search}%"
            statement = statement.where(
                or_(
                    LegacyLibraryFile.filename.like(pattern),
                    LegacyLibraryFile.source_title.like(pattern),
                    LegacyLibraryFile.tags.like(pattern),
                )
            )
        statement = statement.order_by(LegacyLibraryFile.created_at.desc())
        with SessionLocal() as session:
            rows = session.scalars(statement).all()
            return [self._library_from_model(row) for row in rows]

    def update_library_file(self, file_id: str, patch: LibraryFilePatch) -> LibraryFile | None:
        current = self.get_library_file(file_id)
        if not current:
            return None
        data = current.model_dump(mode="json")
        updates = patch.model_dump(exclude_unset=True)
        data.update(updates)
        if "tags" in updates:
            data["tags"] = updates["tags"] or []

        with SessionLocal() as session:
            row = session.get(LegacyLibraryFile, file_id)
            if not row:
                return None
            for column in (
                "filename",
                "subject",
                "category",
                "chapter",
                "source_type",
                "source_authority",
                "source_title",
                "source_publisher",
                "source_code",
                "source_version",
                "year",
            ):
                setattr(row, column, data[column])
            row.tags = json.dumps(data["tags"], ensure_ascii=False)
            session.commit()
            session.refresh(row)
            return self._library_from_model(row)

    def rename_library_subject(self, old_subject: str, new_subject: str) -> None:
        if old_subject == new_subject:
            return
        with SessionLocal() as session:
            rows = session.scalars(select(LegacyLibraryFile).where(LegacyLibraryFile.subject == old_subject)).all()
            for row in rows:
                row.subject = new_subject
            session.commit()

    def set_parsed_text(self, file_id: str, text: str, token_count: int) -> None:
        with SessionLocal() as session:
            row = session.get(LegacyLibraryFile, file_id)
            if row:
                row.parsed_text = text
                row.token_count = token_count
                session.commit()

    def mark_library_used(self, file_id: str) -> None:
        with SessionLocal() as session:
            row = session.get(LegacyLibraryFile, file_id)
            if row:
                row.last_used_at = datetime.utcnow()
                session.commit()

    def delete_library_file(self, file_id: str) -> LibraryFile | None:
        current = self.get_library_file(file_id)
        if not current:
            return None
        with SessionLocal() as session:
            row = session.get(LegacyLibraryFile, file_id)
            if row:
                session.delete(row)
                session.commit()
        return current

    def create_job(self, job: GenerationJob) -> GenerationJob:
        with SessionLocal() as session:
            session.add(self._job_to_model(job))
            session.commit()
        return job

    def update_job(self, job: GenerationJob) -> None:
        values = self._job_values(job)
        with SessionLocal() as session:
            row = session.get(LegacyGenerationJob, job.id)
            if not row:
                return
            row.context = values["context"]
            row.status = values["status"]
            row.result = values["result"]
            row.review = values["review"]
            row.created_at = values["created_at"]
            row.error = values["error"]
            session.commit()

    def get_job(self, job_id: str) -> GenerationJob | None:
        with SessionLocal() as session:
            row = session.get(LegacyGenerationJob, job_id)
            return self._job_from_model(row) if row else None

    def list_jobs(self) -> list[GenerationJob]:
        statement = select(LegacyGenerationJob).order_by(LegacyGenerationJob.created_at.desc())
        with SessionLocal() as session:
            rows = session.scalars(statement).all()
            return [self._job_from_model(row) for row in rows]

    def delete_job(self, job_id: str) -> bool:
        with SessionLocal() as session:
            result = session.execute(delete(LegacyGenerationJob).where(LegacyGenerationJob.id == job_id))
            session.commit()
            return result.rowcount > 0

    def enqueue_task(
        self,
        task_type: str,
        payload: dict[str, Any],
        *,
        max_attempts: int = 3,
        task_id: str | None = None,
    ) -> str:
        now = datetime.utcnow()
        task_id = task_id or str(uuid4())
        with SessionLocal() as session:
            session.add(
                LegacyBackgroundTask(
                    id=task_id,
                    task_type=task_type,
                    payload=json.dumps(payload, ensure_ascii=False),
                    status="queued",
                    attempts=0,
                    max_attempts=max_attempts,
                    last_error=None,
                    worker_id=None,
                    created_at=now,
                    updated_at=now,
                    next_run_at=now,
                    locked_at=None,
                    finished_at=None,
                )
            )
            session.commit()
        return task_id

    def recover_active_tasks(self) -> int:
        now = datetime.utcnow()
        with SessionLocal() as session:
            rows = session.scalars(
                select(LegacyBackgroundTask).where(LegacyBackgroundTask.status.in_(("queued", "running")))
            ).all()
            for row in rows:
                row.status = "queued"
                row.worker_id = None
                row.locked_at = None
                row.next_run_at = now
                row.updated_at = now
            session.commit()
            return len(rows)

    def list_background_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        statement = select(LegacyBackgroundTask).order_by(LegacyBackgroundTask.created_at.desc()).limit(limit)
        with SessionLocal() as session:
            rows = session.scalars(statement).all()
            return [self._background_task_from_model(row) for row in rows]

    def get_background_task(self, task_id: str) -> dict[str, Any] | None:
        with SessionLocal() as session:
            row = session.get(LegacyBackgroundTask, task_id)
            return self._background_task_from_model(row) if row else None

    def claim_next_task(self, worker_id: str) -> dict[str, Any] | None:
        now = datetime.utcnow()
        with SessionLocal() as session:
            row = session.scalar(
                select(LegacyBackgroundTask)
                .where(
                    LegacyBackgroundTask.status == "queued",
                    LegacyBackgroundTask.next_run_at <= now,
                )
                .order_by(LegacyBackgroundTask.created_at.asc())
                .limit(1)
            )
            if not row:
                return None
            result = session.execute(
                update(LegacyBackgroundTask)
                .where(
                    LegacyBackgroundTask.id == row.id,
                    LegacyBackgroundTask.status == "queued",
                    LegacyBackgroundTask.next_run_at <= now,
                )
                .values(
                    status="running",
                    attempts=LegacyBackgroundTask.attempts + 1,
                    worker_id=worker_id,
                    locked_at=now,
                    updated_at=now,
                )
            )
            if result.rowcount != 1:
                session.rollback()
                return None
            session.commit()
            claimed = session.get(LegacyBackgroundTask, row.id)
            return self._background_task_from_model(claimed) if claimed else None

    def complete_task(self, task_id: str) -> None:
        now = datetime.utcnow()
        with SessionLocal() as session:
            row = session.get(LegacyBackgroundTask, task_id)
            if not row:
                return
            row.status = "succeeded"
            row.last_error = None
            row.worker_id = None
            row.updated_at = now
            row.finished_at = now
            session.commit()

    def fail_task(self, task_id: str, error: str, *, retry_delay_seconds: int = 30) -> None:
        now = datetime.utcnow()
        with SessionLocal() as session:
            row = session.get(LegacyBackgroundTask, task_id)
            if not row:
                return
            row.last_error = error
            row.worker_id = None
            row.locked_at = None
            row.updated_at = now
            if row.attempts < row.max_attempts:
                row.status = "queued"
                row.next_run_at = now + timedelta(seconds=retry_delay_seconds)
            else:
                row.status = "failed"
                row.finished_at = now
            session.commit()

    def _background_task_from_model(self, row: LegacyBackgroundTask) -> dict[str, Any]:
        data = self._model_to_dict(row)
        data["payload"] = json.loads(data["payload"] or "{}")
        return data

    def create_topic(
        self,
        topic: WorkflowTopic,
        actor: str | None = None,
        note: str | None = None,
    ) -> WorkflowTopic:
        with SessionLocal() as session:
            session.add(self._topic_to_model(topic))
            self._insert_topic_event(session, topic, "created", actor, note)
            session.commit()
        return topic

    def get_topic(self, topic_id: str) -> WorkflowTopic | None:
        with SessionLocal() as session:
            row = session.get(LegacyWorkflowTopic, topic_id)
            return self._topic_from_model(row) if row else None

    def list_topics(
        self,
        status: str | None = None,
        owner: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        search: str | None = None,
    ) -> list[WorkflowTopic]:
        statement = select(LegacyWorkflowTopic)
        if status:
            statement = statement.where(LegacyWorkflowTopic.status == status)
        if owner:
            statement = statement.where(LegacyWorkflowTopic.owner == owner)
        parsed_date_from = self._parse_date_filter(date_from)
        parsed_date_to = self._parse_date_filter(date_to)
        if parsed_date_from:
            statement = statement.where(LegacyWorkflowTopic.scheduled_date >= parsed_date_from)
        if parsed_date_to:
            statement = statement.where(LegacyWorkflowTopic.scheduled_date <= parsed_date_to)
        if search:
            pattern = f"%{search}%"
            statement = statement.where(
                or_(
                    LegacyWorkflowTopic.title.like(pattern),
                    LegacyWorkflowTopic.brief.like(pattern),
                    LegacyWorkflowTopic.chapter.like(pattern),
                    LegacyWorkflowTopic.content_goal.like(pattern),
                )
            )
        statement = statement.order_by(
            LegacyWorkflowTopic.scheduled_date.is_(None),
            LegacyWorkflowTopic.scheduled_date.asc(),
            LegacyWorkflowTopic.updated_at.desc(),
        )
        with SessionLocal() as session:
            rows = session.scalars(statement).all()
            return [self._topic_from_model(row) for row in rows]

    def update_topic(
        self,
        topic_id: str,
        patch: WorkflowTopicPatch,
        event_type: str = "updated",
    ) -> WorkflowTopic | None:
        current = self.get_topic(topic_id)
        if not current:
            return None

        updates = patch.model_dump(exclude_unset=True)
        actor = updates.pop("actor", None)
        note = updates.pop("note", None)
        if not updates and not note:
            return current

        data = current.model_dump(mode="json")
        data.update(updates)
        data["updated_at"] = datetime.utcnow()
        updated_topic = WorkflowTopic.model_validate(data)

        with SessionLocal() as session:
            row = session.get(LegacyWorkflowTopic, topic_id)
            if not row:
                return None
            self._apply_topic(row, updated_topic)
            self._insert_topic_event(session, updated_topic, event_type, actor, note)
            session.commit()
            session.refresh(row)
            return self._topic_from_model(row)

    def delete_topic(self, topic_id: str) -> bool:
        with SessionLocal() as session:
            result = session.execute(delete(LegacyWorkflowTopic).where(LegacyWorkflowTopic.id == topic_id))
            session.execute(delete(LegacyWorkflowEvent).where(LegacyWorkflowEvent.topic_id == topic_id))
            session.commit()
            return result.rowcount > 0

    def list_topic_events(self, topic_id: str) -> list[WorkflowEvent]:
        statement = (
            select(LegacyWorkflowEvent)
            .where(LegacyWorkflowEvent.topic_id == topic_id)
            .order_by(LegacyWorkflowEvent.version.desc())
        )
        with SessionLocal() as session:
            rows = session.scalars(statement).all()
            return [self._event_from_model(row) for row in rows]

    def _library_to_model(self, file: LibraryFile) -> LegacyLibraryFile:
        data = file.model_dump()
        data["tags"] = json.dumps(data["tags"], ensure_ascii=False)
        return LegacyLibraryFile(**data)

    def _library_from_model(self, row: LegacyLibraryFile) -> LibraryFile:
        data = self._model_to_dict(row)
        data["tags"] = json.loads(data["tags"] or "[]")
        source_title = (data.get("source_title") or "").strip()
        if source_title in {"鎵归噺涓婁紶璧勬枡", "uploaded source"}:
            data["source_title"] = Path(data.get("filename") or "untitled").stem
        return LibraryFile.model_validate(data)

    def _job_values(self, job: GenerationJob) -> dict[str, Any]:
        data = job.model_dump(mode="json")
        return {
            "id": data["id"],
            "context": json.dumps(data["context"], ensure_ascii=False),
            "status": data["status"],
            "result": json.dumps(data["result"], ensure_ascii=False) if data.get("result") else None,
            "review": json.dumps(data["review"], ensure_ascii=False) if data.get("review") else None,
            "created_at": job.created_at,
            "error": data.get("error"),
        }

    def _job_to_model(self, job: GenerationJob) -> LegacyGenerationJob:
        return LegacyGenerationJob(**self._job_values(job))

    def _job_from_model(self, row: LegacyGenerationJob) -> GenerationJob:
        data = self._model_to_dict(row)
        data["context"] = json.loads(data["context"])
        data["result"] = json.loads(data["result"]) if data["result"] else None
        data["review"] = json.loads(data["review"]) if data["review"] else None
        return GenerationJob.model_validate(data)

    def _topic_to_model(self, topic: WorkflowTopic) -> LegacyWorkflowTopic:
        data = self._topic_to_record(topic)
        return LegacyWorkflowTopic(**data)

    def _topic_to_record(self, topic: WorkflowTopic) -> dict[str, Any]:
        data = topic.model_dump()
        data["material_file_ids"] = json.dumps(data["material_file_ids"], ensure_ascii=False)
        data["ragflow_dataset_ids"] = json.dumps(data["ragflow_dataset_ids"], ensure_ascii=False)
        return data

    def _apply_topic(self, row: LegacyWorkflowTopic, topic: WorkflowTopic) -> None:
        data = self._topic_to_record(topic)
        for key, value in data.items():
            setattr(row, key, value)

    def _topic_from_model(self, row: LegacyWorkflowTopic) -> WorkflowTopic:
        data = self._model_to_dict(row)
        data["material_file_ids"] = json.loads(data["material_file_ids"] or "[]")
        data["ragflow_dataset_ids"] = json.loads(data["ragflow_dataset_ids"] or "[]")
        return WorkflowTopic.model_validate(data)

    def _insert_topic_event(
        self,
        session,
        topic: WorkflowTopic,
        event_type: str,
        actor: str | None,
        note: str | None,
    ) -> WorkflowEvent:
        version = (
            session.scalar(
                select(func.coalesce(func.max(LegacyWorkflowEvent.version), 0) + 1).where(
                    LegacyWorkflowEvent.topic_id == topic.id
                )
            )
            or 1
        )
        event = WorkflowEvent(
            id=f"{topic.id}:{version}",
            topic_id=topic.id,
            version=version,
            event_type=event_type,
            note=note,
            actor=actor,
            snapshot=topic.model_dump(mode="json"),
            created_at=datetime.utcnow(),
        )
        session.add(
            LegacyWorkflowEvent(
                id=event.id,
                topic_id=event.topic_id,
                version=event.version,
                event_type=event.event_type,
                note=event.note,
                actor=event.actor,
                snapshot=json.dumps(event.snapshot, ensure_ascii=False),
                created_at=event.created_at,
            )
        )
        return event

    def _event_from_model(self, row: LegacyWorkflowEvent) -> WorkflowEvent:
        data = self._model_to_dict(row)
        data["snapshot"] = json.loads(data["snapshot"] or "{}")
        return WorkflowEvent.model_validate(data)

    def _model_to_dict(self, row) -> dict[str, Any]:
        return {column.name: getattr(row, column.name) for column in row.__table__.columns}

    def _parse_date_filter(self, value: str | None) -> date | None:
        if not value:
            return None
        return date.fromisoformat(value)
