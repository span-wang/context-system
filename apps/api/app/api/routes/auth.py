from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.auth import CurrentUserResponse, LoginRequest, LoginResponse, LogoutRequest, RefreshRequest, RefreshResponse
from app.schemas.common import SimpleMessage
from app.services.auth import AuthService


router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, session: Session = Depends(get_session)) -> LoginResponse:
    return AuthService(session).login(payload.username, payload.password)


@router.post("/refresh", response_model=RefreshResponse)
def refresh(payload: RefreshRequest, session: Session = Depends(get_session)) -> RefreshResponse:
    return AuthService(session).refresh(payload.refresh_token)


@router.get("/me", response_model=CurrentUserResponse)
def me(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> CurrentUserResponse:
    return AuthService(session).get_current_user(credentials.credentials if credentials else None)


@router.post("/logout", response_model=SimpleMessage)
def logout(payload: LogoutRequest, session: Session = Depends(get_session)) -> SimpleMessage:
    AuthService(session).logout(payload.refresh_token)
    return SimpleMessage(message="logout acknowledged")
