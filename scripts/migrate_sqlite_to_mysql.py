from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable
from pathlib import Path

from sqlalchemy import JSON, MetaData, Table, create_engine, delete, func, inspect, select, text
from sqlalchemy.dialects.mysql import insert as mysql_insert


ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "apps" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app.db.base import Base  # noqa: E402
from app.models.legacy import LEGACY_TABLE_NAMES  # noqa: E402


DEFAULT_SQLITE_PATH = ROOT / "data" / "app.db"
DEFAULT_MYSQL_URL = "mysql+pymysql://examkit:examkit123@127.0.0.1:3309/exam_kit_migrate_20260509?charset=utf8mb4"
MYSQL_ONLY_HINT = "Target DB_URL must be a mysql+pymysql URL."
CHUNK_SIZE = 500


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate legacy SQLite data into MySQL.")
    parser.add_argument(
        "--sqlite-path",
        default=str(DEFAULT_SQLITE_PATH),
        help="Path to the existing SQLite database file.",
    )
    parser.add_argument(
        "--mysql-url",
        default=os.getenv("DB_URL") or DEFAULT_MYSQL_URL,
        help="Target MySQL URL. Defaults to DB_URL or the local project MySQL.",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Delete existing data in managed tables before import.",
    )
    parser.add_argument(
        "--skip-nonempty-check",
        action="store_true",
        help="Import even if the target tables already contain rows.",
    )
    return parser.parse_args()


def ensure_mysql_url(url: str) -> str:
    candidate = url.strip()
    if candidate.startswith("mysql+pymysql://"):
        return candidate
    if candidate.startswith("mysql://"):
        return f"mysql+pymysql://{candidate.removeprefix('mysql://')}"
    raise SystemExit(MYSQL_ONLY_HINT)


def resolve_source_tables(sqlite_engine) -> dict[str, Table]:
    metadata = MetaData()
    metadata.reflect(bind=sqlite_engine)
    return metadata.tables


def iter_model_tables() -> list[Table]:
    return list(Base.metadata.sorted_tables)


def table_has_rows(engine, table: Table) -> bool:
    with engine.connect() as connection:
        return connection.execute(select(func.count()).select_from(table)).scalar_one() > 0


def delete_existing_rows(engine, tables: Iterable[Table]) -> None:
    with engine.begin() as connection:
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in reversed(list(tables)):
            connection.execute(delete(table))
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 1"))


def rows_as_dicts(source_conn, source_table: Table, columns: list[str]) -> Iterable[list[dict[str, object]]]:
    result = source_conn.execute(select(*(source_table.c[name] for name in columns)))
    while True:
        rows = result.fetchmany(CHUNK_SIZE)
        if not rows:
            break
        yield [dict(row._mapping) for row in rows]


def normalize_batch_for_target(batch: list[dict[str, object]], target_table: Table) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    json_columns = {
        column.name
        for column in target_table.columns
        if isinstance(column.type, JSON)
    }
    for row in batch:
        converted: dict[str, object] = {}
        for key, value in row.items():
            if key in json_columns and isinstance(value, str):
                try:
                    converted[key] = json.loads(value)
                except json.JSONDecodeError:
                    converted[key] = value
            else:
                converted[key] = value
        normalized.append(converted)
    return normalized


def copy_table(source_conn, target_conn, source_tables: dict[str, Table], target_table: Table) -> tuple[int, int]:
    source_table = source_tables.get(target_table.name)
    if source_table is None:
        return (0, 0)

    target_columns = [column.name for column in target_table.columns]
    source_columns = [name for name in target_columns if name in source_table.c]
    skipped_columns = len(target_columns) - len(source_columns)
    inserted_rows = 0

    for batch in rows_as_dicts(source_conn, source_table, source_columns):
        if not batch:
            continue
        target_conn.execute(mysql_insert(target_table), normalize_batch_for_target(batch, target_table))
        inserted_rows += len(batch)
    return (inserted_rows, skipped_columns)


def check_target_is_ready(mysql_engine, tables: list[Table], skip_nonempty_check: bool) -> None:
    existing_tables = set(inspect(mysql_engine).get_table_names())
    missing = [table.name for table in tables if table.name not in existing_tables]
    if missing:
        preview = ", ".join(missing[:8])
        raise SystemExit(
            "Target MySQL schema is missing Alembic-managed tables. "
            f"Run migrations first. Missing: {preview}"
        )
    if skip_nonempty_check:
        return
    nonempty = [table.name for table in tables if table_has_rows(mysql_engine, table)]
    if nonempty:
        preview = ", ".join(nonempty[:8])
        raise SystemExit(
            "Target MySQL already contains data. Re-run with --truncate or --skip-nonempty-check. "
            f"Non-empty tables: {preview}"
        )


def main() -> int:
    args = parse_args()
    sqlite_path = Path(args.sqlite_path).resolve()
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite source database not found: {sqlite_path}")

    sqlite_url = f"sqlite:///{sqlite_path.as_posix()}"
    mysql_url = ensure_mysql_url(args.mysql_url)
    sqlite_engine = create_engine(sqlite_url)
    mysql_engine = create_engine(mysql_url)
    source_tables = resolve_source_tables(sqlite_engine)

    managed_tables = iter_model_tables()
    check_target_is_ready(mysql_engine, managed_tables, args.skip_nonempty_check or args.truncate)

    if args.truncate:
        delete_existing_rows(mysql_engine, managed_tables)

    print(f"SQLite source: {sqlite_path}")
    print(f"MySQL target: {mysql_url}")

    total_rows = 0
    copied_tables = 0
    with sqlite_engine.connect() as source_conn:
        with mysql_engine.begin() as target_conn:
            target_conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
            try:
                for table in managed_tables:
                    inserted_rows, skipped_columns = copy_table(source_conn, target_conn, source_tables, table)
                    if inserted_rows == 0 and table.name not in source_tables:
                        print(f"- {table.name}: skipped (not present in SQLite source)")
                        continue
                    copied_tables += 1
                    total_rows += inserted_rows
                    legacy_mark = " legacy" if table.name in LEGACY_TABLE_NAMES else ""
                    if skipped_columns:
                        print(
                            f"- {table.name}:{legacy_mark} inserted {inserted_rows} rows "
                            f"(source missing {skipped_columns} target columns)"
                        )
                    else:
                        print(f"- {table.name}:{legacy_mark} inserted {inserted_rows} rows")
            finally:
                target_conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

    print(f"Done. Copied {total_rows} rows across {copied_tables} tables.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
