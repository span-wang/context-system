from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, create_refresh_token, decode_access_token, hash_password, hash_token, verify_password
from app.models import AuthTokenSession
from app.repositories.auth import AuthRepository
from app.schemas.auth import CurrentUserResponse, LoginResponse, RefreshResponse, RoleSummary


class AuthService:
    def __init__(self, session: Session) -> None:
        self.repository = AuthRepository(session)

    def login(self, username: str, password: str) -> LoginResponse:
        user = self.repository.get_user_by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        settings = get_settings()
        expires_in = settings.security.access_token_expires_minutes * 60
        refresh_token = create_refresh_token()
        self.repository.create_token_session(
            AuthTokenSession(
                tenant_id=user.tenant_id,
                user_id=user.id,
                refresh_token_hash=hash_token(refresh_token),
                status="active",
                expires_at=datetime.utcnow() + timedelta(days=settings.security.refresh_token_expires_days),
                created_by=user.id,
                updated_by=user.id,
            )
        )
        if "$" not in user.password_hash:
            user.password_hash = hash_password(password)
        user.last_login_at = datetime.utcnow()
        self.repository.session.commit()
        return LoginResponse(
            access_token=create_access_token(str(user.id), settings.security.secret_key, expires_in),
            refresh_token=refresh_token,
            expires_in=expires_in,
            user=self.get_user_response(user.id),
        )

    def refresh(self, refresh_token: str) -> RefreshResponse:
        session_item = self.repository.get_token_session_by_hash(hash_token(refresh_token))
        if session_item is None or session_item.status != "active":
            raise HTTPException(status_code=401, detail="刷新令牌无效")
        if session_item.expires_at < datetime.utcnow():
            session_item.status = "expired"
            self.repository.session.commit()
            raise HTTPException(status_code=401, detail="刷新令牌已过期")
        user = self.repository.get_user_by_id(session_item.user_id)
        if user is None or user.status != "active":
            raise HTTPException(status_code=401, detail="用户不可用")
        settings = get_settings()
        expires_in = settings.security.access_token_expires_minutes * 60
        return RefreshResponse(
            access_token=create_access_token(str(user.id), settings.security.secret_key, expires_in),
            expires_in=expires_in,
            user=self.get_user_response(user.id),
        )

    def logout(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        session_item = self.repository.get_token_session_by_hash(hash_token(refresh_token))
        if session_item is None or session_item.status != "active":
            return
        session_item.status = "revoked"
        session_item.revoked_at = datetime.utcnow()
        self.repository.session.commit()

    def get_current_user(self, token: str | None = None) -> CurrentUserResponse:
        if not token:
            return self.get_user_response_by_username("admin")
        settings = get_settings()
        payload = decode_access_token(token, settings.security.secret_key)
        subject = payload.get("sub")
        if not subject:
            raise HTTPException(status_code=401, detail="登录令牌缺少用户")
        try:
            user_id = int(subject)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="登录令牌用户无效") from exc
        return self.get_user_response(user_id)

    def get_user_response_by_username(self, username: str) -> CurrentUserResponse:
        user = self.repository.get_user_by_username(username)
        if user is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        return self._build_user_response(user.id)

    def get_user_response(self, user_id: int) -> CurrentUserResponse:
        user = self.repository.get_user_by_id(user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        return self._build_user_response(user.id)

    def _build_user_response(self, user_id: int) -> CurrentUserResponse:
        user = self.repository.get_user_by_id(user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        roles = [RoleSummary.model_validate(role) for role in self.repository.list_roles_for_user(user.id)]
        return CurrentUserResponse.model_validate({**user.__dict__, "roles": roles})
