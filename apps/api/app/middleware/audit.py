from __future__ import annotations

import logging
from typing import Callable

from fastapi import Request, Response
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models import AuditLog


logger = logging.getLogger(__name__)


class FailedRequestAuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        if not _should_log(request, response):
            return response

        try:
            with SessionLocal() as session:
                session.add(
                    AuditLog(
                        tenant_id=1,
                        user_id=_resolve_user_id(request),
                        module="http",
                        action="failed_request",
                        target_type=request.method,
                        target_id=request.url.path,
                        request_id=request.headers.get("x-request-id"),
                        payload_json={
                            "status_code": response.status_code,
                            "query": str(request.url.query)[:500],
                        },
                    )
                )
                session.commit()
        except Exception:
            logger.exception("Failed to audit failed request: %s %s", request.method, request.url.path)
        return response


def _should_log(request: Request, response: Response) -> bool:
    if response.status_code < 400:
        return False
    path = request.url.path
    return path.startswith("/api/") or path.startswith("/platform/api/")


def _resolve_user_id(request: Request) -> int | None:
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token, get_settings().security.secret_key)
        subject = payload.get("sub")
        return int(subject) if subject else None
    except Exception:
        return None
