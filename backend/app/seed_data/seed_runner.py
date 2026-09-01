from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.allowlists import ALLOWED_ACTIONS
from app.models.industry_template import IndustryTemplate
from app.repositories.industry_template import IndustryTemplateRepository
from app.seed_data.industry_templates import ALL_TEMPLATES, TemplateDefinition


@dataclass
class SeedResult:
    created: list[str]
    skipped: list[str]


def _validate_definition(definition: TemplateDefinition) -> None:
    invalid_actions = set(definition.actions) - ALLOWED_ACTIONS
    if invalid_actions:
        raise ValueError(f"Template {definition.key!r} uses unknown action(s): {invalid_actions}")
    # Constructing this validates the qualification fields (unique keys,
    # supported types, option requirements, etc.) via Pydantic.
    definition.qualification_schema_json()


def seed_industry_templates(db: Session) -> SeedResult:
    """Idempotent, rerunnable: an existing (key, version) row is NEVER
    modified — only missing (key, version) combinations are inserted. To
    change a template's content, add a new TemplateDefinition with a bumped
    version; this function will insert it as a new row and leave every
    earlier version (and every tenant that already selected one) untouched.
    """
    repo = IndustryTemplateRepository(db)
    result = SeedResult(created=[], skipped=[])

    for definition in ALL_TEMPLATES:
        _validate_definition(definition)

        existing = repo.get_by_key_and_version(definition.key, definition.version)
        if existing is not None:
            result.skipped.append(f"{definition.key}:v{definition.version}")
            continue

        template = IndustryTemplate(
            key=definition.key,
            version=definition.version,
            name=definition.name,
            description=definition.description,
            icon=definition.icon,
            default_terminology=definition.terminology,
            default_welcome_message=definition.welcome_message,
            default_suggested_questions=definition.suggested_questions,
            default_qualification_schema=definition.qualification_schema_json(),
            default_actions=definition.actions,
            default_safety_rules=definition.safety_rules,
            default_workflow=definition.workflow_stages,
            is_active=True,
        )
        repo.add(template)
        result.created.append(f"{definition.key}:v{definition.version}")

    db.flush()
    return result
