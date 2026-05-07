from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog
from app.repositories.auth import AuthRepository
from app.repositories.audit import AuditRepository
from app.schemas.auth import CurrentUserResponse
from app.schemas.system import AuditLogResponse


class AuditService:
    def __init__(self, session: Session) -> None:
        self.repository = AuditRepository(session)

    def log(
        self,
        user: CurrentUserResponse,
        module: str,
        action: str,
        target_type: str | None = None,
        target_id: str | int | None = None,
        payload: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> AuditLog:
        log = self.repository.create_log(
            AuditLog(
                tenant_id=1,
                user_id=user.id,
                module=module,
                action=action,
                target_type=target_type,
                target_id=str(target_id) if target_id is not None else None,
                request_id=None,
                payload_json=_safe_payload(payload),
                created_by=user.id,
                updated_by=user.id,
            )
        )
        if commit:
            self.repository.session.commit()
        return log

    def list_logs(self, limit: int = 50) -> list[AuditLogResponse]:
        rows = self.repository.list_logs(max(1, min(limit, 200)))
        auth_repository = AuthRepository(self.repository.session)
        responses: list[AuditLogResponse] = []
        for row in rows:
            user = auth_repository.get_user_by_id(row.user_id) if row.user_id else None
            responses.append(
                AuditLogResponse(
                    id=row.id,
                    user_id=row.user_id,
                    module=row.module,
                    action=row.action,
                    target_type=row.target_type,
                    target_id=row.target_id,
                    payload_json=row.payload_json,
                    created_at=row.created_at,
                    username=user.username if user else None,
                )
            )
        return responses


def _safe_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    safe = dict(payload)
    for key in list(safe):
        if "password" in key.lower() or "token" in key.lower():
            safe[key] = "***"
    return safe
