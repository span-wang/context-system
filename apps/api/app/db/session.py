from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


settings = get_settings()
database_url = settings.db.resolved_url
if not database_url.startswith("mysql"):
    raise RuntimeError("Only MySQL is supported. Configure DB_URL with a mysql+pymysql URL.")

engine_kwargs = {
    "echo": settings.db.echo,
    "pool_pre_ping": True,
    "pool_recycle": 3600,
    "pool_size": settings.db.pool_size,
    "max_overflow": settings.db.max_overflow,
}

engine = create_engine(database_url, **engine_kwargs)


@event.listens_for(engine, "connect")
def _configure_mysql_connection(dbapi_connection, connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("SET NAMES utf8mb4")
    cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
