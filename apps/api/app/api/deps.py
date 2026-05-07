from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.auth import CurrentUserResponse
from app.services.auth import AuthService


def get_session(session: Session = Depends(get_db_session)) -> Session:
    return session


bearer = HTTPBearer(auto_error=False)


def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> CurrentUserResponse:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return AuthService(session).get_current_user(credentials.credentials)


def require_roles(*allowed_roles: str):
    def dependency(current_user: CurrentUserResponse = Depends(require_user)) -> CurrentUserResponse:
        role_codes = {role.role_code for role in current_user.roles}
        if "super_admin" in role_codes or role_codes.intersection(allowed_roles):
            return current_user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权执行该操作")

    return dependency
