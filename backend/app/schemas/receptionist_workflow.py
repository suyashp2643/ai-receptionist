import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.allowlists import ALLOWED_ACTIONS
from app.core.text_safety import MAX_SHORT_TEXT, validate_plain_text
from app.schemas.qualification import QualificationRules, QualificationSchema

MAX_ENABLED_ACTIONS = len(ALLOWED_ACTIONS)
MAX_SAFETY_RULES = 40
MAX_WORKFLOW_STAGES = 20


def _validate_enabled_actions(v: list[str]) -> list[str]:
    invalid = set(v) - ALLOWED_ACTIONS
    if invalid:
        raise ValueError(f"Unknown action(s): {sorted(invalid)}")
    if len(v) != len(set(v)):
        raise ValueError("Duplicate actions are not allowed.")
    return v


def _validate_safety_rules(v: list[str]) -> list[str]:
    if len(v) > MAX_SAFETY_RULES:
        raise ValueError(f"Too many safety rules (max {MAX_SAFETY_RULES}).")
    return [validate_plain_text(rule, max_length=500) for rule in v]


def _validate_workflow_stages(v: list[str]) -> list[str]:
    if len(v) > MAX_WORKFLOW_STAGES:
        raise ValueError(f"Too many workflow stages (max {MAX_WORKFLOW_STAGES}).")
    return [validate_plain_text(stage, max_length=MAX_SHORT_TEXT) for stage in v]


class ReceptionistWorkflowUpdate(BaseModel):
    qualification_schema: QualificationSchema | None = None
    qualification_rules: QualificationRules | None = None
    enabled_actions: list[str] | None = None
    safety_rules: list[str] | None = None
    workflow_stages: list[str] | None = None

    @field_validator("enabled_actions")
    @classmethod
    def _actions(cls, v: list[str] | None) -> list[str] | None:
        return _validate_enabled_actions(v) if v is not None else None

    @field_validator("safety_rules")
    @classmethod
    def _safety(cls, v: list[str] | None) -> list[str] | None:
        return _validate_safety_rules(v) if v is not None else None

    @field_validator("workflow_stages")
    @classmethod
    def _stages(cls, v: list[str] | None) -> list[str] | None:
        return _validate_workflow_stages(v) if v is not None else None


class ReceptionistWorkflowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    receptionist_id: uuid.UUID
    qualification_schema: dict
    qualification_rules: dict
    enabled_actions: list
    safety_rules: list
    workflow_stages: list
    version: int
    created_at: datetime
    updated_at: datetime
