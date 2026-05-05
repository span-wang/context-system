from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from schemas.generation import GenerationJob
from schemas.library import LibraryFile, LibraryFilePatch
from schemas.workflow import WorkflowEvent, WorkflowTopic, WorkflowTopicPatch


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS library_files (
                    id TEXT PRIMARY KEY,
                    sha256 TEXT NOT NULL UNIQUE,
                    filename TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    mime TEXT NOT NULL,
                    storage_path TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    category TEXT,
                    chapter TEXT,
                    source_type TEXT NOT NULL,
                    source_authority TEXT NOT NULL,
                    source_title TEXT NOT NULL,
                    source_publisher TEXT,
                    source_code TEXT,
                    source_version TEXT,
                    year INTEGER,
                    tags TEXT NOT NULL,
                    parsed_text TEXT,
                    token_count INTEGER,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS generation_jobs (
                    id TEXT PRIMARY KEY,
                    context TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result TEXT,
                    review TEXT,
                    created_at TEXT NOT NULL,
                    error TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_topics (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    brief TEXT,
                    subject TEXT NOT NULL,
                    category TEXT,
                    chapter TEXT,
                    content_type TEXT NOT NULL,
                    owner TEXT,
                    status TEXT NOT NULL,
                    review_status TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    scheduled_date TEXT,
                    due_date TEXT,
                    publish_channel TEXT NOT NULL,
                    content_goal TEXT,
                    audience TEXT,
                    material_file_ids TEXT NOT NULL,
                    ragflow_dataset_ids TEXT NOT NULL,
                    generation_job_id TEXT,
                    confirmed_by TEXT,
                    confirmed_at TEXT,
                    published_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_events (
                    id TEXT PRIMARY KEY,
                    topic_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    note TEXT,
                    actor TEXT,
                    snapshot TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_workflow_topics_status
                ON workflow_topics(status)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_workflow_topics_schedule
                ON workflow_topics(scheduled_date)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_workflow_events_topic
                ON workflow_events(topic_id, version)
                """
            )
            conn.commit()

    def insert_library_file(self, file: LibraryFile) -> LibraryFile:
        data = file.model_dump(mode="json")
        data["tags"] = json.dumps(data["tags"], ensure_ascii=False)
        columns = ", ".join(data.keys())
        placeholders = ", ".join([f":{key}" for key in data])
        with self.connect() as conn:
            conn.execute(
                f"INSERT INTO library_files ({columns}) VALUES ({placeholders})",
                data,
            )
            conn.commit()
        return file

    def get_library_by_sha(self, sha256: str) -> LibraryFile | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM library_files WHERE sha256 = ?", (sha256,)).fetchone()
        return self._library_from_row(row) if row else None

    def get_library_file(self, file_id: str) -> LibraryFile | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM library_files WHERE id = ?", (file_id,)).fetchone()
        return self._library_from_row(row) if row else None

    def list_library_files(
        self,
        subject: str | None = None,
        category: str | None = None,
        source_type: str | None = None,
        search: str | None = None,
    ) -> list[LibraryFile]:
        clauses: list[str] = []
        values: list[Any] = []
        if subject:
            clauses.append("subject = ?")
            values.append(subject)
        if category:
            clauses.append("category = ?")
            values.append(category)
        if source_type:
            clauses.append("source_type = ?")
            values.append(source_type)
        if search:
            clauses.append("(filename LIKE ? OR source_title LIKE ? OR tags LIKE ?)")
            pattern = f"%{search}%"
            values.extend([pattern, pattern, pattern])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM library_files {where} ORDER BY created_at DESC",
                values,
            ).fetchall()
        return [self._library_from_row(row) for row in rows]

    def update_library_file(self, file_id: str, patch: LibraryFilePatch) -> LibraryFile | None:
        current = self.get_library_file(file_id)
        if not current:
            return None
        data = current.model_dump(mode="json")
        updates = patch.model_dump(exclude_unset=True)
        data.update(updates)
        if "tags" in updates:
            data["tags"] = updates["tags"] or []
        data["tags"] = json.dumps(data["tags"], ensure_ascii=False)
        columns = [
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
            "tags",
        ]
        assignments = ", ".join([f"{column} = :{column}" for column in columns])
        data["id"] = file_id
        with self.connect() as conn:
            conn.execute(f"UPDATE library_files SET {assignments} WHERE id = :id", data)
            conn.commit()
        return self.get_library_file(file_id)

    def rename_library_subject(self, old_subject: str, new_subject: str) -> None:
        if old_subject == new_subject:
            return
        with self.connect() as conn:
            conn.execute(
                "UPDATE library_files SET subject = ? WHERE subject = ?",
                (new_subject, old_subject),
            )
            conn.commit()

    def set_parsed_text(self, file_id: str, text: str, token_count: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE library_files SET parsed_text = ?, token_count = ? WHERE id = ?",
                (text, token_count, file_id),
            )
            conn.commit()

    def mark_library_used(self, file_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE library_files SET last_used_at = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), file_id),
            )
            conn.commit()

    def delete_library_file(self, file_id: str) -> LibraryFile | None:
        current = self.get_library_file(file_id)
        if not current:
            return None
        with self.connect() as conn:
            conn.execute("DELETE FROM library_files WHERE id = ?", (file_id,))
            conn.commit()
        return current

    def create_job(self, job: GenerationJob) -> GenerationJob:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO generation_jobs
                    (id, context, status, result, review, created_at, error)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                self._job_values(job),
            )
            conn.commit()
        return job

    def update_job(self, job: GenerationJob) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE generation_jobs
                SET context = ?, status = ?, result = ?, review = ?, created_at = ?, error = ?
                WHERE id = ?
                """,
                (*self._job_values(job)[1:], job.id),
            )
            conn.commit()

    def get_job(self, job_id: str) -> GenerationJob | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM generation_jobs WHERE id = ?", (job_id,)).fetchone()
        return self._job_from_row(row) if row else None

    def list_jobs(self) -> list[GenerationJob]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM generation_jobs ORDER BY created_at DESC"
            ).fetchall()
        return [self._job_from_row(row) for row in rows]

    def delete_job(self, job_id: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM generation_jobs WHERE id = ?", (job_id,))
            conn.commit()
        return cur.rowcount > 0

    def create_topic(
        self,
        topic: WorkflowTopic,
        actor: str | None = None,
        note: str | None = None,
    ) -> WorkflowTopic:
        data = self._topic_to_record(topic)
        columns = ", ".join(data.keys())
        placeholders = ", ".join([f":{key}" for key in data])
        with self.connect() as conn:
            conn.execute(
                f"INSERT INTO workflow_topics ({columns}) VALUES ({placeholders})",
                data,
            )
            self._insert_topic_event(conn, topic, "created", actor, note)
            conn.commit()
        return topic

    def get_topic(self, topic_id: str) -> WorkflowTopic | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM workflow_topics WHERE id = ?", (topic_id,)).fetchone()
        return self._topic_from_row(row) if row else None

    def list_topics(
        self,
        status: str | None = None,
        owner: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        search: str | None = None,
    ) -> list[WorkflowTopic]:
        clauses: list[str] = []
        values: list[Any] = []
        if status:
            clauses.append("status = ?")
            values.append(status)
        if owner:
            clauses.append("owner = ?")
            values.append(owner)
        if date_from:
            clauses.append("scheduled_date >= ?")
            values.append(date_from)
        if date_to:
            clauses.append("scheduled_date <= ?")
            values.append(date_to)
        if search:
            clauses.append("(title LIKE ? OR brief LIKE ? OR chapter LIKE ? OR content_goal LIKE ?)")
            pattern = f"%{search}%"
            values.extend([pattern, pattern, pattern, pattern])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM workflow_topics
                {where}
                ORDER BY
                    CASE WHEN scheduled_date IS NULL THEN 1 ELSE 0 END,
                    scheduled_date ASC,
                    updated_at DESC
                """,
                values,
            ).fetchall()
        return [self._topic_from_row(row) for row in rows]

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
        data["updated_at"] = datetime.utcnow().isoformat()
        record = self._topic_to_record(WorkflowTopic.model_validate(data))
        columns = [
            "title",
            "brief",
            "subject",
            "category",
            "chapter",
            "content_type",
            "owner",
            "status",
            "review_status",
            "priority",
            "scheduled_date",
            "due_date",
            "publish_channel",
            "content_goal",
            "audience",
            "material_file_ids",
            "ragflow_dataset_ids",
            "generation_job_id",
            "confirmed_by",
            "confirmed_at",
            "published_at",
            "updated_at",
        ]
        assignments = ", ".join([f"{column} = :{column}" for column in columns])
        with self.connect() as conn:
            conn.execute(f"UPDATE workflow_topics SET {assignments} WHERE id = :id", record)
            updated = self._topic_from_row(
                conn.execute("SELECT * FROM workflow_topics WHERE id = ?", (topic_id,)).fetchone()
            )
            self._insert_topic_event(conn, updated, event_type, actor, note)
            conn.commit()
        return updated

    def delete_topic(self, topic_id: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM workflow_topics WHERE id = ?", (topic_id,))
            conn.execute("DELETE FROM workflow_events WHERE topic_id = ?", (topic_id,))
            conn.commit()
        return cur.rowcount > 0

    def list_topic_events(self, topic_id: str) -> list[WorkflowEvent]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM workflow_events WHERE topic_id = ? ORDER BY version DESC",
                (topic_id,),
            ).fetchall()
        return [self._event_from_row(row) for row in rows]

    def _library_from_row(self, row: sqlite3.Row) -> LibraryFile:
        data = dict(row)
        data["tags"] = json.loads(data["tags"] or "[]")
        source_title = (data.get("source_title") or "").strip()
        if source_title in {"批量上传资料", "uploaded source"}:
            data["source_title"] = Path(data.get("filename") or "未命名资料").stem
        return LibraryFile.model_validate(data)

    def _job_values(self, job: GenerationJob) -> tuple[Any, ...]:
        data = job.model_dump(mode="json")
        return (
            data["id"],
            json.dumps(data["context"], ensure_ascii=False),
            data["status"],
            json.dumps(data["result"], ensure_ascii=False) if data.get("result") else None,
            json.dumps(data["review"], ensure_ascii=False) if data.get("review") else None,
            data["created_at"],
            data.get("error"),
        )

    def _job_from_row(self, row: sqlite3.Row) -> GenerationJob:
        data = dict(row)
        data["context"] = json.loads(data["context"])
        data["result"] = json.loads(data["result"]) if data["result"] else None
        data["review"] = json.loads(data["review"]) if data["review"] else None
        return GenerationJob.model_validate(data)

    def _topic_to_record(self, topic: WorkflowTopic) -> dict[str, Any]:
        data = topic.model_dump(mode="json")
        data["material_file_ids"] = json.dumps(data["material_file_ids"], ensure_ascii=False)
        data["ragflow_dataset_ids"] = json.dumps(data["ragflow_dataset_ids"], ensure_ascii=False)
        return data

    def _topic_from_row(self, row: sqlite3.Row) -> WorkflowTopic:
        data = dict(row)
        data["material_file_ids"] = json.loads(data["material_file_ids"] or "[]")
        data["ragflow_dataset_ids"] = json.loads(data["ragflow_dataset_ids"] or "[]")
        return WorkflowTopic.model_validate(data)

    def _insert_topic_event(
        self,
        conn: sqlite3.Connection,
        topic: WorkflowTopic,
        event_type: str,
        actor: str | None,
        note: str | None,
    ) -> WorkflowEvent:
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 AS version FROM workflow_events WHERE topic_id = ?",
            (topic.id,),
        ).fetchone()
        event = WorkflowEvent(
            id=f"{topic.id}:{row['version']}",
            topic_id=topic.id,
            version=row["version"],
            event_type=event_type,
            note=note,
            actor=actor,
            snapshot=topic.model_dump(mode="json"),
            created_at=datetime.utcnow(),
        )
        conn.execute(
            """
            INSERT INTO workflow_events
                (id, topic_id, version, event_type, note, actor, snapshot, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.topic_id,
                event.version,
                event.event_type,
                event.note,
                event.actor,
                json.dumps(event.snapshot, ensure_ascii=False),
                event.created_at.isoformat(),
            ),
        )
        return event

    def _event_from_row(self, row: sqlite3.Row) -> WorkflowEvent:
        data = dict(row)
        data["snapshot"] = json.loads(data["snapshot"] or "{}")
        return WorkflowEvent.model_validate(data)
