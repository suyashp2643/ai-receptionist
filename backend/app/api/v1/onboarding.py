from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_db, get_tenant_context, require_tenant_role
from app.models.enums import TenantMemberRole
from app.schemas.business_profile import (
    BusinessProfileRead,
    BusinessProfileUpdate,
    OnboardingState,
    SelectIndustryRequest,
)
from app.services import onboarding_service

router = APIRouter()


@router.get("/tenants/{tenant_id}/onboarding", response_model=OnboardingState)
def get_onboarding_state(
    ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)
) -> OnboardingState:
    return onboarding_service.compute_onboarding_state(db, tenant_id=ctx.tenant_id)


@router.patch("/tenants/{tenant_id}/business-profile", response_model=BusinessProfileRead)
def update_business_profile(
    payload: BusinessProfileUpdate,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> BusinessProfileRead:
    profile = onboarding_service.update_business_profile(db, tenant_id=ctx.tenant_id, payload=payload)
    return BusinessProfileRead.model_validate(profile)


@router.post("/tenants/{tenant_id}/select-industry", response_model=BusinessProfileRead)
def select_industry(
    payload: SelectIndustryRequest,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> BusinessProfileRead:
    try:
        profile, _receptionist, _workflow = onboarding_service.select_industry(
            db, tenant_id=ctx.tenant_id, template_key=payload.template_key
        )
    except onboarding_service.UnknownIndustryTemplateError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return BusinessProfileRead.model_validate(profile)


@router.post("/tenants/{tenant_id}/complete-onboarding", response_model=BusinessProfileRead)
def complete_onboarding(
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> BusinessProfileRead | JSONResponse:
    try:
        profile = onboarding_service.complete_onboarding(db, tenant_id=ctx.tenant_id)
    except onboarding_service.OnboardingNotReadyError as exc:
        # A structured `requirements` list (not just a string message) so
        # the frontend can link the user directly to the step that needs
        # attention, rather than showing one opaque error string.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "message": "Onboarding requirements are not met yet.",
                    "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "requirements": jsonable_encoder([r.model_dump() for r in exc.requirements]),
                }
            },
        )
    return BusinessProfileRead.model_validate(profile)
