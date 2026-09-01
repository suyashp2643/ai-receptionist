from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.industry_template import IndustryTemplateDetail, IndustryTemplateSummary
from app.services import industry_template_service

router = APIRouter()


@router.get("/industry-templates", response_model=list[IndustryTemplateSummary])
def list_industry_templates(
    _current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[IndustryTemplateSummary]:
    """Global, read-only catalog — every authenticated user can view it,
    nobody (tenant owner or otherwise) can write to it through this API."""
    templates = industry_template_service.list_catalog(db)
    return [IndustryTemplateSummary.model_validate(t) for t in templates]


@router.get("/industry-templates/{key}", response_model=IndustryTemplateDetail)
def get_industry_template(
    key: str, _current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> IndustryTemplateDetail:
    template = industry_template_service.get_by_key(db, key)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Industry template not found")
    return IndustryTemplateDetail.model_validate(template)
