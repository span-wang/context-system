from __future__ import annotations

from sqlalchemy.orm import Session


class Repository:
    def __init__(self, session: Session) -> None:
        self.session = session
