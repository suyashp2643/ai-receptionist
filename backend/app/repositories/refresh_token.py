import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        return self.db.scalars(stmt).first()

    def add(self, token: RefreshToken) -> RefreshToken:
        self.db.add(token)
        return token

    def revoke(self, token: RefreshToken) -> None:
        token.revoked_at = datetime.now(UTC)

    def revoke_family(self, family_id: uuid.UUID) -> None:
        """Revokes every non-revoked token in a family — used on reuse detection
        and on logout, so a stolen or logged-out session can't be refreshed again."""
        now = datetime.now(UTC)
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        self.db.execute(stmt)

    def delete_expired(self, *, before: datetime) -> int:
        """Housekeeping helper (not wired to a scheduler yet — Phase 2 scope is
        the mechanism, not an automated cleanup job)."""
        stmt = select(RefreshToken).where(RefreshToken.expires_at < before)
        expired = self.db.scalars(stmt).all()
        for token in expired:
            self.db.delete(token)
        return len(expired)
