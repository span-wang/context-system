from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class RoleSummary(ORMModel):
    id: int
    role_code: str
    role_name: str


class CurrentUserResponse(ORMModel):
    id: int
    username: str
    display_name: str
    email: str | None = None
    mobile: str | None = None
    user_type: str
    status: str
    last_login_at: datetime | None = None
    roles: list[RoleSummary]


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: CurrentUserResponse


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: CurrentUserResponse
