import uuid
from collections.abc import Sequence
from typing import Generic, Protocol, TypeVar, runtime_checkable

from sqlalchemy import select
from sqlalchemy.orm import Session


@runtime_checkable
class HasTenantAndId(Protocol):
    id: uuid.UUID
    tenant_id: uuid.UUID


ModelT = TypeVar("ModelT", bound=HasTenantAndId)


class TenantScopedRepository(Generic[ModelT]):
    """Base for repositories over tables that carry a `tenant_id` column.

    `tenant_id` must come from a trusted server-side source (the resolved
    `TenantContext`), never from a client-supplied value — callers are
    responsible for that; this class only guarantees every query it runs is
    filtered by the `tenant_id` it was constructed with.

    Deliberately NOT a place for "convenience" global lookups — anything
    that needs to bypass tenant scoping (User, future IndustryTemplate)
    must use its own plain repository instead, so unscoped access stays
    explicit and grep-able rather than hidden behind a shared base class.
    """

    model: type[ModelT]

    def __init__(self, db: Session, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id

    def add(self, obj: ModelT) -> ModelT:
        """Caller is responsible for having set obj.tenant_id == self.tenant_id
        before calling this — it does not stamp it automatically, so that
        assignment stays visible at the call site rather than implicit here."""
        self.db.add(obj)
        return obj

    def get(self, resource_id: uuid.UUID) -> ModelT | None:
        # mypy can't see through the Protocol bound that `.id`/`.tenant_id`
        # are SQLAlchemy InstrumentedAttributes (whose `==` returns a
        # ColumnElement, not bool) — correct at runtime; see HasTenantAndId.
        stmt = select(self.model).where(
            self.model.id == resource_id,  # type: ignore[arg-type]
            self.model.tenant_id == self.tenant_id,  # type: ignore[arg-type]
        )
        return self.db.scalars(stmt).first()

    def list(self) -> Sequence[ModelT]:
        stmt = select(self.model).where(self.model.tenant_id == self.tenant_id)  # type: ignore[arg-type]
        return self.db.scalars(stmt).all()

    def delete(self, resource_id: uuid.UUID) -> bool:
        """Deletes only if the resource belongs to this repository's tenant."""
        obj = self.get(resource_id)
        if obj is None:
            return False
        self.db.delete(obj)
        return True
