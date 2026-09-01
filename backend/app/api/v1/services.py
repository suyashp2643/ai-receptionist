import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_db, get_tenant_context, require_tenant_role
from app.models.enums import TenantMemberRole
from app.models.service import Service
from app.repositories.business_location import BusinessLocationRepository
from app.repositories.service import ServiceRepository
from app.schemas.service import ServiceCreate, ServiceRead, ServiceUpdate

router = APIRouter()


def _get_service_or_404(service_id: uuid.UUID, ctx: TenantContext, db: Session) -> Service:
    service = ServiceRepository(db, ctx.tenant_id).get(service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return service


def _validate_location_id(location_id: uuid.UUID | None, ctx: TenantContext, db: Session) -> None:
    """A service's location_id must belong to THIS tenant — otherwise a
    client could link a service to another tenant's location by UUID alone,
    since the FK itself doesn't know about tenant boundaries."""
    if location_id is None:
        return
    if BusinessLocationRepository(db, ctx.tenant_id).get(location_id) is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown location_id")


@router.get("/tenants/{tenant_id}/services", response_model=list[ServiceRead])
def list_services(ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)) -> list[ServiceRead]:
    services = ServiceRepository(db, ctx.tenant_id).list_ordered()
    return [ServiceRead.model_validate(s) for s in services]


@router.post("/tenants/{tenant_id}/services", response_model=ServiceRead, status_code=status.HTTP_201_CREATED)
def create_service(
    payload: ServiceCreate,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> ServiceRead:
    _validate_location_id(payload.location_id, ctx, db)
    service = Service(tenant_id=ctx.tenant_id, **payload.model_dump())
    ServiceRepository(db, ctx.tenant_id).add(service)
    db.flush()
    return ServiceRead.model_validate(service)


@router.get("/tenants/{tenant_id}/services/{service_id}", response_model=ServiceRead)
def get_service(
    service_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> ServiceRead:
    service = _get_service_or_404(service_id, ctx, db)
    return ServiceRead.model_validate(service)


@router.patch("/tenants/{tenant_id}/services/{service_id}", response_model=ServiceRead)
def update_service(
    service_id: uuid.UUID,
    payload: ServiceUpdate,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> ServiceRead:
    service = _get_service_or_404(service_id, ctx, db)
    data = payload.model_dump(exclude_unset=True)
    if "location_id" in data:
        _validate_location_id(data["location_id"], ctx, db)
    for field, value in data.items():
        setattr(service, field, value)
    return ServiceRead.model_validate(service)


@router.delete("/tenants/{tenant_id}/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service(
    service_id: uuid.UUID,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> None:
    service = _get_service_or_404(service_id, ctx, db)
    db.delete(service)
