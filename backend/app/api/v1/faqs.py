import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_db, get_tenant_context, require_tenant_role
from app.models.enums import TenantMemberRole
from app.models.faq import FAQ
from app.repositories.faq import FAQRepository
from app.schemas.faq import FAQCreate, FAQCreateResult, FAQRead, FAQUpdate

router = APIRouter()


def _get_faq_or_404(faq_id: uuid.UUID, ctx: TenantContext, db: Session) -> FAQ:
    faq = FAQRepository(db, ctx.tenant_id).get(faq_id)
    if faq is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FAQ not found")
    return faq


@router.get("/tenants/{tenant_id}/faqs", response_model=list[FAQRead])
def list_faqs(ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)) -> list[FAQRead]:
    faqs = FAQRepository(db, ctx.tenant_id).list_ordered()
    return [FAQRead.model_validate(f) for f in faqs]


@router.post("/tenants/{tenant_id}/faqs", response_model=FAQCreateResult, status_code=status.HTTP_201_CREATED)
def create_faq(
    payload: FAQCreate,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> FAQCreateResult:
    repo = FAQRepository(db, ctx.tenant_id)
    duplicate = repo.find_similar_question(payload.question)

    faq = FAQ(tenant_id=ctx.tenant_id, **payload.model_dump())
    repo.add(faq)
    db.flush()
    return FAQCreateResult(faq=FAQRead.model_validate(faq), possible_duplicate_of=duplicate.id if duplicate else None)


@router.get("/tenants/{tenant_id}/faqs/{faq_id}", response_model=FAQRead)
def get_faq(
    faq_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> FAQRead:
    faq = _get_faq_or_404(faq_id, ctx, db)
    return FAQRead.model_validate(faq)


@router.patch("/tenants/{tenant_id}/faqs/{faq_id}", response_model=FAQRead)
def update_faq(
    faq_id: uuid.UUID,
    payload: FAQUpdate,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> FAQRead:
    faq = _get_faq_or_404(faq_id, ctx, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(faq, field, value)
    return FAQRead.model_validate(faq)


@router.delete("/tenants/{tenant_id}/faqs/{faq_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_faq(
    faq_id: uuid.UUID,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> None:
    faq = _get_faq_or_404(faq_id, ctx, db)
    db.delete(faq)
