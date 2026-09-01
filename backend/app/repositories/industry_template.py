import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.industry_template import IndustryTemplate


class IndustryTemplateRepository:
    """Plain (non-tenant-scoped) repository — templates are global catalog
    data. No method here ever accepts tenant input as authoritative, and
    nothing in this class mutates a template on a tenant's behalf."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, template_id: uuid.UUID) -> IndustryTemplate | None:
        return self.db.get(IndustryTemplate, template_id)

    def get_latest_active_by_key(self, key: str) -> IndustryTemplate | None:
        stmt = (
            select(IndustryTemplate)
            .where(IndustryTemplate.key == key, IndustryTemplate.is_active.is_(True))
            .order_by(IndustryTemplate.version.desc())
        )
        return self.db.scalars(stmt).first()

    def get_by_key_and_version(self, key: str, version: int) -> IndustryTemplate | None:
        stmt = select(IndustryTemplate).where(IndustryTemplate.key == key, IndustryTemplate.version == version)
        return self.db.scalars(stmt).first()

    def list_latest_active(self) -> list[IndustryTemplate]:
        """One row per key — the highest active version of each template."""
        all_active = self.db.scalars(
            select(IndustryTemplate)
            .where(IndustryTemplate.is_active.is_(True))
            .order_by(IndustryTemplate.key, IndustryTemplate.version.desc())
        ).all()
        latest_by_key: dict[str, IndustryTemplate] = {}
        for template in all_active:
            latest_by_key.setdefault(template.key, template)
        return list(latest_by_key.values())

    def add(self, template: IndustryTemplate) -> IndustryTemplate:
        self.db.add(template)
        return template
