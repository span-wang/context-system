from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from schemas.generation import GenerationJob
from schemas.library import LibraryFile, LibraryFilePatch


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

    def _library_from_row(self, row: sqlite3.Row) -> LibraryFile:
        data = dict(row)
        data["tags"] = json.loads(data["tags"] or "[]")
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

