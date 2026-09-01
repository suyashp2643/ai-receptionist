import uuid

from sqlalchemy.orm import Session

from app.models.business_location import BusinessLocation
from app.repositories.business_location import BusinessLocationRepository
from app.schemas.business_location import BusinessLocationCreate, BusinessLocationUpdate


def _unset_other_primaries(db: Session, *, tenant_id: uuid.UUID, keep: uuid.UUID | None) -> None:
    repo = BusinessLocationRepository(db, tenant_id)
    for other in repo.list_ordered():
        if other.id != keep and other.is_primary:
            other.is_primary = False
    # Flush the unset BEFORE the new primary is set, so the two updates never
    # both hold is_primary=true at once — required for the partial unique
    # index (see BusinessLocation.__table_args__) to never transiently reject
    # a legitimate swap within the same transaction.
    db.flush()


def create_location(db: Session, *, tenant_id: uuid.UUID, payload: BusinessLocationCreate) -> BusinessLocation:
    location = BusinessLocation(
        tenant_id=tenant_id,
        name=payload.name,
        address_line=payload.address_line,
        city=payload.city,
        region=payload.region,
        country=payload.country,
        postal_code=payload.postal_code,
        timezone=payload.timezone,
        public_phone=payload.public_phone,
        working_hours=payload.working_hours.model_dump(mode="json"),
        is_primary=False,
        is_active=payload.is_active,
    )
    BusinessLocationRepository(db, tenant_id).add(location)
    db.flush()

    if payload.is_primary:
        _unset_other_primaries(db, tenant_id=tenant_id, keep=location.id)
        location.is_primary = True

    return location


def update_location(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    location: BusinessLocation,
    payload: BusinessLocationUpdate,
) -> BusinessLocation:
    data = payload.model_dump(exclude_unset=True)
    wants_primary = data.pop("is_primary", None)
    if "working_hours" in data:
        data["working_hours"] = payload.working_hours.model_dump(mode="json") if payload.working_hours else {}

    for field, value in data.items():
        setattr(location, field, value)

    if wants_primary is True and not location.is_primary:
        _unset_other_primaries(db, tenant_id=tenant_id, keep=location.id)
        location.is_primary = True
    elif wants_primary is False:
        location.is_primary = False

    return location
