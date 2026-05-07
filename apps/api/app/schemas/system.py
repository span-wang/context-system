from __future__ import annotations

from typing import Literal
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import HealthResponse


class PlatformSummary(BaseModel):
    current_phase: str
    database_url: str
    storage_type: str
    mysql_ready: bool
    database_type: str
    migration_target: str
    auto_migrate: bool
    seed_on_startup: bool
    alembic_current_revision: str | None = None
    alembic_head_revision: str | None = None
    migration_status: str
    migration_ready: bool
    database_ping_ok: bool
    module_status: dict[str, str]


class SystemStatusResponse(BaseModel):
    health: HealthResponse
    summary: PlatformSummary


class OCRCapabilityResponse(BaseModel):
    status: Literal["ok", "warn", "fail"]
    summary: str
    device_name: str | None = None
    gpu_memory_total_mb: int | None = None
    gpu_memory_free_mb: int | None = None
    cuda_available: bool
    paddle_version: str | None = None
    paddle_cuda_device_count: int | None = None
    recommended_pipeline: str
    current_settings: dict[str, object]
    warnings: list[str]
    checks: dict[str, object]


class AuditLogResponse(BaseModel):
    id: int
    user_id: int | None = None
    module: str
    action: str
    target_type: str | None = None
    target_id: str | None = None
    payload_json: dict | None = None
    created_at: datetime
    username: str | None = None
