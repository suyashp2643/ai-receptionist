import uuid

from sqlalchemy.orm import Session

from app.core.allowlists import MANDATORY_SAFETY_RULES
from app.models.industry_template import IndustryTemplate
from app.models.receptionist import Receptionist
from app.models.receptionist_workflow import ReceptionistWorkflow
from app.repositories.industry_template import IndustryTemplateRepository
from app.repositories.receptionist import ReceptionistRepository, ReceptionistWorkflowRepository
from app.schemas.receptionist import ReceptionistCreate, ReceptionistUpdate
from app.schemas.receptionist_workflow import ReceptionistWorkflowUpdate


class MandatorySafetyRuleRemovedError(ValueError):
    def __init__(self, template_key: str, missing_rules: list[str]):
        self.template_key = template_key
        self.missing_rules = missing_rules
        super().__init__(
            f"The following safety rules are mandatory for {template_key!r} "
            f"receptionists and cannot be removed: {missing_rules}"
        )


def create_receptionist(
    db: Session, *, tenant_id: uuid.UUID, payload: ReceptionistCreate
) -> tuple[Receptionist, ReceptionistWorkflow]:
    """Every receptionist always gets a workflow row created alongside it —
    GET .../workflow should never 404 for a receptionist that exists."""
    receptionist = Receptionist(
        tenant_id=tenant_id,
        name=payload.name,
        welcome_message=payload.welcome_message,
        tone=payload.tone,
        default_language=payload.default_language,
        supported_languages=payload.supported_languages,
        logo_url=payload.logo_url,
        accent_color=payload.accent_color,
        suggested_questions=payload.suggested_questions,
    )
    ReceptionistRepository(db, tenant_id).add(receptionist)
    db.flush()

    workflow = ReceptionistWorkflow(
        tenant_id=tenant_id,
        receptionist_id=receptionist.id,
        qualification_schema={"fields": []},
        qualification_rules={"rules": []},
        enabled_actions=[],
        safety_rules=[],
        workflow_stages=[],
    )
    ReceptionistWorkflowRepository(db, tenant_id).add(workflow)
    db.flush()

    return receptionist, workflow


def update_receptionist(receptionist: Receptionist, payload: ReceptionistUpdate) -> Receptionist:
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(receptionist, field, value)
    return receptionist


def apply_template_defaults(
    db: Session,
    *,
    receptionist: Receptionist,
    workflow: ReceptionistWorkflow,
    template: IndustryTemplate,
) -> None:
    """Selecting a template snapshots its current defaults into the tenant's
    OWN rows — later edits to the global template never retroactively change
    this tenant's configuration. Only applied when the workflow looks
    untouched (no qualification fields, no enabled actions yet) so a
    re-selection never clobbers real tenant customization."""
    receptionist.industry_template_id = template.id
    receptionist.template_version = template.version
    if not receptionist.welcome_message:
        receptionist.welcome_message = template.default_welcome_message
    if not receptionist.suggested_questions:
        receptionist.suggested_questions = list(template.default_suggested_questions)

    looks_untouched = not workflow.qualification_schema.get("fields") and not workflow.enabled_actions
    if looks_untouched:
        workflow.qualification_schema = dict(template.default_qualification_schema)
        workflow.enabled_actions = list(template.default_actions)
        workflow.safety_rules = list(template.default_safety_rules)
        workflow.workflow_stages = list(template.default_workflow)


def update_workflow(
    db: Session,
    *,
    receptionist: Receptionist,
    workflow: ReceptionistWorkflow,
    payload: ReceptionistWorkflowUpdate,
) -> ReceptionistWorkflow:
    data = payload.model_dump(exclude_unset=True)

    if "safety_rules" in data:
        _enforce_mandatory_safety_rules(db, receptionist=receptionist, new_safety_rules=data["safety_rules"])

    for field, value in data.items():
        setattr(workflow, field, value)
    workflow.version += 1
    return workflow


def _enforce_mandatory_safety_rules(db: Session, *, receptionist: Receptionist, new_safety_rules: list[str]) -> None:
    if receptionist.industry_template_id is None:
        return
    template = IndustryTemplateRepository(db).get_by_id(receptionist.industry_template_id)
    if template is None:
        return
    mandatory = MANDATORY_SAFETY_RULES.get(template.key)
    if not mandatory:
        return
    missing = [rule for rule in mandatory if rule not in new_safety_rules]
    if missing:
        raise MandatorySafetyRuleRemovedError(template.key, missing)
