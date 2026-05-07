from __future__ import annotations

from sqlalchemy import select

from app.models import AuditLog
from app.repositories.base import Repository


class AuditRepository(Repository):
    def create_log(self, log: AuditLog) -> AuditLog:
        self.session.add(log)
        self.session.flush()
        return log

    def list_logs(self, limit: int = 50) -> list[AuditLog]:
        stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
        return list(self.session.scalars(stmt))
