import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_db, get_tenant_context, require_tenant_role
from app.models.business_location import BusinessLocation
from app.models.enums import TenantMemberRole
from app.repositories.business_location import BusinessLocationRepository
from app.schemas.business_location import (
    BusinessLocationCreate,
    BusinessLocationRead,
    BusinessLocationUpdate,
)
from app.services import location_service

router = APIRouter()


def _get_location_or_404(location_id: uuid.UUID, ctx: TenantContext, db: Session) -> BusinessLocation:
    location = BusinessLocationRepository(db, ctx.tenant_id).get(location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return location


@router.get("/tenants/{tenant_id}/locations", response_model=list[BusinessLocationRead])
def list_locations(
    ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)
) -> list[BusinessLocationRead]:
    locations = BusinessLocationRepository(db, ctx.tenant_id).list_ordered()
    return [BusinessLocationRead.model_validate(loc) for loc in locations]


@router.post(
    "/tenants/{tenant_id}/locations",
    response_model=BusinessLocationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_location(
    payload: BusinessLocationCreate,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> BusinessLocationRead:
    location = location_service.create_location(db, tenant_id=ctx.tenant_id, payload=payload)
    return BusinessLocationRead.model_validate(location)


@router.get("/tenants/{tenant_id}/locations/{location_id}", response_model=BusinessLocationRead)
def get_location(
    location_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> BusinessLocationRead:
    location = _get_location_or_404(location_id, ctx, db)
    return BusinessLocationRead.model_validate(location)


@router.patch("/tenants/{tenant_id}/locations/{location_id}", response_model=BusinessLocationRead)
def update_location(
    location_id: uuid.UUID,
    payload: BusinessLocationUpdate,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> BusinessLocationRead:
    location = _get_location_or_404(location_id, ctx, db)
    location_service.update_location(db, tenant_id=ctx.tenant_id, location=location, payload=payload)
    return BusinessLocationRead.model_validate(location)


@router.delete("/tenants/{tenant_id}/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_location(
    location_id: uuid.UUID,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> None:
    location = _get_location_or_404(location_id, ctx, db)
    db.delete(location)
