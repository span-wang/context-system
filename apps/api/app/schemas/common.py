from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SimpleMessage(BaseModel):
    message: str


class HealthResponse(BaseModel):
    ok: bool
    name: str
    version: str
    environment: str
