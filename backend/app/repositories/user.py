import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    """Plain (non-tenant-scoped) repository — User is a global model."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.db.get(User, user_id)

    def get_by_normalized_email(self, normalized_email: str) -> User | None:
        stmt = select(User).where(User.normalized_email == normalized_email)
        return self.db.scalars(stmt).first()

    def add(self, user: User) -> User:
        self.db.add(user)
        return user
