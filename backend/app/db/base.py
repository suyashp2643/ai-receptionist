from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models.

    No tenant-owned models are defined in Phase 1 — this exists so Alembic
    and future model modules have a stable import target.
    """
