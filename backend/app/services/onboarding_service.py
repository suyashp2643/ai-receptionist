import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.business_profile import BusinessProfile
from app.models.enums import ContentStatus, OnboardingStatus, ReceptionistStatus
from app.models.receptionist import Receptionist
from app.models.receptionist_workflow import ReceptionistWorkflow
from app.repositories.business_location import BusinessLocationRepository
from app.repositories.business_profile import BusinessProfileRepository
from app.repositories.faq import FAQRepository
from app.repositories.industry_template import IndustryTemplateRepository
from app.repositories.knowledge import KnowledgeDocumentRepository
from app.repositories.receptionist import ReceptionistRepository, ReceptionistWorkflowRepository
from app.repositories.service import ServiceRepository
from app.schemas.business_profile import (
    BusinessProfileRead,
    BusinessProfileUpdate,
    OnboardingRequirement,
    OnboardingState,
    OnboardingStepStatus,
)
from app.schemas.receptionist import ReceptionistCreate
from app.services.receptionist_service import apply_template_defaults, create_receptionist


class UnknownIndustryTemplateError(ValueError):
    pass


class OnboardingNotReadyError(ValueError):
    def __init__(self, requirements: list[OnboardingRequirement]):
        self.requirements = requirements
        super().__init__(f"Onboarding is not ready to complete: {[r.code for r in requirements]}")


def get_or_create_business_profile(db: Session, *, tenant_id: uuid.UUID) -> BusinessProfile:
    repo = BusinessProfileRepository(db)
    profile = repo.get_by_tenant_id(tenant_id)
    if profile is None:
        profile = BusinessProfile(tenant_id=tenant_id)
        repo.add(profile)
        db.flush()
    return profile


def update_business_profile(db: Session, *, tenant_id: uuid.UUID, payload: BusinessProfileUpdate) -> BusinessProfile:
    profile = get_or_create_business_profile(db, tenant_id=tenant_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(profile, field, value)
    if profile.onboarding_status == OnboardingStatus.NOT_STARTED:
        profile.onboarding_status = OnboardingStatus.IN_PROGRESS
    return profile


def select_industry(
    db: Session, *, tenant_id: uuid.UUID, template_key: str
) -> tuple[BusinessProfile, Receptionist, ReceptionistWorkflow]:
    template = IndustryTemplateRepository(db).get_latest_active_by_key(template_key)
    if template is None:
        raise UnknownIndustryTemplateError(f"Unknown or inactive industry template: {template_key!r}")

    profile = get_or_create_business_profile(db, tenant_id=tenant_id)
    profile.industry_template_id = template.id
    if profile.onboarding_status == OnboardingStatus.NOT_STARTED:
        profile.onboarding_status = OnboardingStatus.IN_PROGRESS

    receptionist_repo = ReceptionistRepository(db, tenant_id)
    receptionists = receptionist_repo.list_ordered()
    if receptionists:
        receptionist = receptionists[0]
        workflow = ReceptionistWorkflowRepository(db, tenant_id).get_by_receptionist_id(receptionist.id)
        assert workflow is not None  # every receptionist always has one — see create_receptionist
    else:
        receptionist, workflow = create_receptionist(
            db,
            tenant_id=tenant_id,
            payload=ReceptionistCreate(name=template.name + " Receptionist"),
        )

    apply_template_defaults(db, receptionist=receptionist, workflow=workflow, template=template)
    return profile, receptionist, workflow


def _has_active_knowledge(db: Session, *, tenant_id: uuid.UUID) -> bool:
    has_active_faq = any(f.is_active for f in FAQRepository(db, tenant_id).list())
    if has_active_faq:
        return True
    return any(d.status == ContentStatus.ACTIVE for d in KnowledgeDocumentRepository(db, tenant_id).list())


def _compute_requirements(
    *,
    profile: BusinessProfile,
    receptionist: Receptionist | None,
    workflow: ReceptionistWorkflow | None,
    has_active_knowledge: bool,
) -> list[OnboardingRequirement]:
    """The minimum bar for a *usable* receptionist. Deliberately does NOT
    require a location or service — some SaaS/online businesses have
    neither, and requiring them would block a legitimately complete setup.
    """
    requirements: list[OnboardingRequirement] = []

    if not profile.business_name:
        requirements.append(
            OnboardingRequirement(code="business_profile", message="Add your business name.", step="business")
        )
    if profile.industry_template_id is None:
        requirements.append(
            OnboardingRequirement(code="industry_template", message="Select an industry template.", step="industry")
        )
    if not (receptionist and receptionist.name and receptionist.welcome_message):
        requirements.append(
            OnboardingRequirement(
                code="receptionist_named",
                message="Name your receptionist and add a welcome message.",
                step="receptionist",
            )
        )
    if not (receptionist and workflow and receptionist.status == ReceptionistStatus.ACTIVE):
        requirements.append(
            OnboardingRequirement(
                code="workflow_active",
                message="Activate your receptionist once you're ready to go live.",
                step="receptionist",
            )
        )
    if not (workflow and workflow.enabled_actions):
        requirements.append(
            OnboardingRequirement(
                code="enabled_actions",
                message="Enable at least one action your receptionist is allowed to take.",
                step="actions",
            )
        )
    if not has_active_knowledge:
        requirements.append(
            OnboardingRequirement(
                code="knowledge_or_faq",
                message="Add at least one active FAQ or active knowledge document.",
                step="knowledge",
            )
        )

    return requirements


def compute_onboarding_state(db: Session, *, tenant_id: uuid.UUID) -> OnboardingState:
    profile = get_or_create_business_profile(db, tenant_id=tenant_id)
    receptionists = ReceptionistRepository(db, tenant_id).list_ordered()
    receptionist = receptionists[0] if receptionists else None
    workflow = (
        ReceptionistWorkflowRepository(db, tenant_id).get_by_receptionist_id(receptionist.id) if receptionist else None
    )
    has_active_knowledge = _has_active_knowledge(db, tenant_id=tenant_id)

    steps = OnboardingStepStatus(
        business_profile=bool(profile.business_name),
        industry_selected=profile.industry_template_id is not None,
        receptionist=bool(receptionist and receptionist.name and receptionist.welcome_message),
        locations=len(BusinessLocationRepository(db, tenant_id).list()) > 0,
        services=len(ServiceRepository(db, tenant_id).list()) > 0,
        knowledge=has_active_knowledge,
        qualification=bool(workflow and workflow.qualification_schema.get("fields")),
        actions=bool(workflow and workflow.enabled_actions),
    )

    # Computed fresh from CURRENT data every time, regardless of the stored
    # onboarding_status. This is what lets an already-`completed` tenant
    # still see accurate configuration warnings if something regresses
    # later (see complete_onboarding for why status itself never reverts).
    requirements = _compute_requirements(
        profile=profile, receptionist=receptionist, workflow=workflow, has_active_knowledge=has_active_knowledge
    )

    return OnboardingState(
        status=profile.onboarding_status,
        completed_at=profile.onboarding_completed_at,
        ready_to_complete=len(requirements) == 0,
        steps=steps,
        incomplete_requirements=requirements,
        business_profile=BusinessProfileRead.model_validate(profile),
    )


def complete_onboarding(db: Session, *, tenant_id: uuid.UUID) -> BusinessProfile:
    """Product decision (documented): completion is monotonic — once a
    tenant reaches `completed`, later configuration changes that regress
    below the minimum bar (e.g. deactivating the last FAQ) do NOT revert
    onboarding_status. Reverting a live tenant's completed state would be a
    confusing, surprising side effect of an unrelated edit (e.g. losing
    dashboard access because a receptionist got paused), and later phases
    may gate real functionality (e.g. widget visibility) on this status —
    an unexpected revert there would be a worse failure mode than briefly
    showing a configuration warning. `compute_onboarding_state` still
    reports the same `incomplete_requirements` list in this case, which the
    frontend presents as warnings rather than blockers once already
    completed. Calling this again after completion is therefore a no-op
    that returns the current profile unchanged.
    """
    profile = get_or_create_business_profile(db, tenant_id=tenant_id)
    if profile.onboarding_status == OnboardingStatus.COMPLETED:
        return profile

    state = compute_onboarding_state(db, tenant_id=tenant_id)
    if state.incomplete_requirements:
        raise OnboardingNotReadyError(state.incomplete_requirements)

    profile.onboarding_status = OnboardingStatus.COMPLETED
    profile.onboarding_completed_at = datetime.now(UTC)
    return profile
