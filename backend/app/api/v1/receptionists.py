import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_db, get_tenant_context, require_tenant_role
from app.models.enums import TenantMemberRole
from app.models.receptionist import Receptionist
from app.repositories.receptionist import ReceptionistRepository, ReceptionistWorkflowRepository
from app.schemas.receptionist import ReceptionistCreate, ReceptionistRead, ReceptionistUpdate
from app.schemas.receptionist_workflow import ReceptionistWorkflowRead, ReceptionistWorkflowUpdate
from app.services import receptionist_service

router = APIRouter()


def _get_receptionist_or_404(receptionist_id: uuid.UUID, ctx: TenantContext, db: Session) -> Receptionist:
    receptionist = ReceptionistRepository(db, ctx.tenant_id).get(receptionist_id)
    if receptionist is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receptionist not found")
    return receptionist


@router.get("/tenants/{tenant_id}/receptionists", response_model=list[ReceptionistRead])
def list_receptionists(
    ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)
) -> list[ReceptionistRead]:
    receptionists = ReceptionistRepository(db, ctx.tenant_id).list_ordered()
    return [ReceptionistRead.model_validate(r) for r in receptionists]


@router.post(
    "/tenants/{tenant_id}/receptionists",
    response_model=ReceptionistRead,
    status_code=status.HTTP_201_CREATED,
)
def create_receptionist(
    payload: ReceptionistCreate,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> ReceptionistRead:
    receptionist, _workflow = receptionist_service.create_receptionist(db, tenant_id=ctx.tenant_id, payload=payload)
    return ReceptionistRead.model_validate(receptionist)


@router.get("/tenants/{tenant_id}/receptionists/{receptionist_id}", response_model=ReceptionistRead)
def get_receptionist(
    receptionist_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> ReceptionistRead:
    receptionist = _get_receptionist_or_404(receptionist_id, ctx, db)
    return ReceptionistRead.model_validate(receptionist)


@router.patch("/tenants/{tenant_id}/receptionists/{receptionist_id}", response_model=ReceptionistRead)
def update_receptionist(
    receptionist_id: uuid.UUID,
    payload: ReceptionistUpdate,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> ReceptionistRead:
    receptionist = _get_receptionist_or_404(receptionist_id, ctx, db)
    receptionist_service.update_receptionist(receptionist, payload)
    return ReceptionistRead.model_validate(receptionist)


@router.get(
    "/tenants/{tenant_id}/receptionists/{receptionist_id}/workflow",
    response_model=ReceptionistWorkflowRead,
)
def get_workflow(
    receptionist_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> ReceptionistWorkflowRead:
    _get_receptionist_or_404(receptionist_id, ctx, db)
    workflow = ReceptionistWorkflowRepository(db, ctx.tenant_id).get_by_receptionist_id(receptionist_id)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return ReceptionistWorkflowRead.model_validate(workflow)


@router.patch(
    "/tenants/{tenant_id}/receptionists/{receptionist_id}/workflow",
    response_model=ReceptionistWorkflowRead,
)
def update_workflow(
    receptionist_id: uuid.UUID,
    payload: ReceptionistWorkflowUpdate,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> ReceptionistWorkflowRead:
    receptionist = _get_receptionist_or_404(receptionist_id, ctx, db)
    workflow = ReceptionistWorkflowRepository(db, ctx.tenant_id).get_by_receptionist_id(receptionist_id)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    try:
        receptionist_service.update_workflow(db, receptionist=receptionist, workflow=workflow, payload=payload)
    except receptionist_service.MandatorySafetyRuleRemovedError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return ReceptionistWorkflowRead.model_validate(workflow)
