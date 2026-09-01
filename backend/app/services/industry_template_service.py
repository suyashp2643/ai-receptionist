from sqlalchemy.orm import Session

from app.models.industry_template import IndustryTemplate
from app.repositories.industry_template import IndustryTemplateRepository


def list_catalog(db: Session) -> list[IndustryTemplate]:
    """Latest active version of every template key — what onboarding shows."""
    return IndustryTemplateRepository(db).list_latest_active()


def get_by_key(db: Session, key: str) -> IndustryTemplate | None:
    return IndustryTemplateRepository(db).get_latest_active_by_key(key)
