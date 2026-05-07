from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session, require_roles
from app.schemas.auth import CurrentUserResponse
from app.schemas.system import AuditLogResponse, OCRCapabilityResponse
from app.services.audit import AuditService
from app.services.system import SystemService


router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/healthz")
def healthz():
    status = SystemService().get_status()
    return status.health.model_dump()


@router.get("/status")
def status():
    return SystemService().get_status()


@router.get("/ocr-capability", response_model=OCRCapabilityResponse)
def ocr_capability() -> OCRCapabilityResponse:
    return SystemService().get_ocr_capability()


@router.get("/audit-logs", response_model=list[AuditLogResponse])
def audit_logs(
    limit: int = Query(default=30, ge=1, le=200),
    session: Session = Depends(get_session),
    _: CurrentUserResponse = Depends(require_roles("super_admin", "admin", "viewer")),
) -> list[AuditLogResponse]:
    return AuditService(session).list_logs(limit)
