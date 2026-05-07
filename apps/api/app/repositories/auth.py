from __future__ import annotations

from sqlalchemy import select

from app.models import AuthTokenSession, Role, User, UserRole
from app.repositories.base import Repository


class AuthRepository(Repository):
    def get_user_by_username(self, username: str) -> User | None:
        return self.session.scalar(select(User).where(User.username == username))

    def list_roles_for_user(self, user_id: int) -> list[Role]:
        stmt = (
            select(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
            .order_by(Role.id.asc())
        )
        return list(self.session.scalars(stmt))

    def get_user_by_id(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def create_token_session(self, item: AuthTokenSession) -> AuthTokenSession:
        self.session.add(item)
        self.session.flush()
        return item

    def get_token_session_by_hash(self, refresh_token_hash: str) -> AuthTokenSession | None:
        return self.session.scalar(select(AuthTokenSession).where(AuthTokenSession.refresh_token_hash == refresh_token_hash))
