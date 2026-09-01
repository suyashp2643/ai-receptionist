import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IndustryTemplateSummary(BaseModel):
    """Used in the catalog listing — enough to render an industry picker."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    version: int
    name: str
    description: str
    icon: str


class IndustryTemplateDetail(IndustryTemplateSummary):
    default_terminology: dict
    default_welcome_message: str
    default_suggested_questions: list
    default_qualification_schema: dict
    default_actions: list
    default_safety_rules: list
    default_workflow: list
    is_active: bool
    created_at: datetime
    updated_at: datetime
