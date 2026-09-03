"""Phase 7 PUBLIC marketing-site demo data: three FICTIONAL businesses (a
clinic, a hotel, and a real-estate agency) embedded on the public website's
own /demo/* pages via the real, unmodified public widget bundle and API.

Deliberately distinct from app/seed_data/demo_tenants.py (Phase 3's
internal, login-based dashboard-exploration demos): these tenants have NO
user, NO tenant_member, and NO password anywhere — "if demo users are
unnecessary, do not create them" — because the public widget API never
requires a dashboard login at all. Only a Tenant row, a Receptionist
(industry-templated), and one ACTIVE WidgetInstallation with a fixed,
memorable public_id (public_id is not a secret by design — see
WidgetInstallation's docstring) exist for each.

Idempotent — re-running skips any demo tenant whose fixed slug already
exists. Safe to run in development only (enforced by the calling script,
same as demo_tenants.py).
"""

from dataclasses import dataclass
from typing import Literal, cast

from sqlalchemy.orm import Session

from app.models.enums import KnowledgeSourceType, ReceptionistStatus, WidgetInstallationStatus
from app.models.faq import FAQ
from app.models.service import Service
from app.models.tenant import Tenant
from app.models.widget_installation import WidgetInstallation
from app.repositories.faq import FAQRepository
from app.repositories.service import ServiceRepository
from app.repositories.tenant import TenantRepository
from app.schemas.business_location import BusinessLocationCreate
from app.schemas.qualification import DayWorkingHours, WorkingHours, WorkingInterval
from app.schemas.receptionist import ReceptionistUpdate
from app.services import knowledge_service, location_service, onboarding_service
from app.services.receptionist_service import update_receptionist


def _six_day_hours(*, start: str, end: str) -> WorkingHours:
    """Monday-Saturday open, Sunday closed — used by the clinic and
    real-estate demos so the mock provider's hours-keyword tool (which
    answers from WorkingHours, not from FAQ text) has real data instead of
    honestly reporting hours as unconfigured."""
    _DayOfWeek = Literal[0, 1, 2, 3, 4, 5, 6]
    days = [
        DayWorkingHours(day_of_week=cast(_DayOfWeek, d), intervals=[WorkingInterval(start=start, end=end)])
        for d in range(6)
    ]
    days.append(DayWorkingHours(day_of_week=6, closed=True, intervals=[]))
    return WorkingHours(days=days)


def _seven_day_hours(*, start: str, end: str) -> WorkingHours:
    _DayOfWeek = Literal[0, 1, 2, 3, 4, 5, 6]
    return WorkingHours(
        days=[
            DayWorkingHours(day_of_week=cast(_DayOfWeek, d), intervals=[WorkingInterval(start=start, end=end)])
            for d in range(7)
        ]
    )


@dataclass
class PublicDemoSpec:
    slug: str
    public_id: str
    tenant_name: str
    industry_key: str
    receptionist_name: str
    welcome_message: str
    suggested_questions: list[str]
    location_name: str
    city: str
    country: str
    working_hours: WorkingHours
    services: list[tuple[str, str]]  # (name, price_note)
    faqs: list[tuple[str, str]]
    knowledge_title: str
    knowledge_text: str


PUBLIC_DEMO_SPECS: list[PublicDemoSpec] = [
    PublicDemoSpec(
        slug="public-demo-clinic",
        public_id="demo-clinic-sunrise",
        tenant_name="Sunrise Family Clinic (Public Demo)",
        industry_key="clinic",
        receptionist_name="Sunrise Family Clinic Assistant",
        welcome_message=(
            "Hi, I'm the virtual assistant for Sunrise Family Clinic. I can answer questions about our "
            "services and hours, or help you request an appointment. How can I help?"
        ),
        suggested_questions=[
            "What services do you offer?",
            "Are you open on Saturday?",
            "I need an appointment tomorrow.",
        ],
        location_name="Sunrise Family Clinic — Main Office",
        city="Riverbend",
        country="USA",
        working_hours=_six_day_hours(start="08:00", end="17:00"),
        services=[
            ("General checkup", "Covered by most insurance plans"),
            ("Vaccinations", "Walk-ins welcome"),
            ("Routine bloodwork", "Fasting required — details provided at booking"),
        ],
        faqs=[
            (
                "What services do you offer?",
                "[FICTIONAL DEMO DATA] Sunrise Family Clinic offers general checkups, vaccinations, "
                "routine bloodwork, and referrals to specialists when needed.",
            ),
            (
                "Are you open on Saturday?",
                "[FICTIONAL DEMO DATA] Yes — Sunrise Family Clinic is open Monday through Saturday, "
                "8am to 5pm, and closed on Sundays.",
            ),
        ],
        knowledge_title="About Sunrise Family Clinic",
        knowledge_text=(
            "[FICTIONAL DEMO DATA] Sunrise Family Clinic is a general-practice family clinic in "
            "Riverbend, open Monday through Saturday from 8am to 5pm. We offer general checkups, "
            "vaccinations, routine bloodwork, and can refer patients to specialists when needed. "
            "Our front-desk team can help schedule an appointment or answer questions about "
            "insurance and office policies. For any medical emergency, please call 911 or go to "
            "your nearest emergency room immediately — this assistant cannot diagnose, prescribe, "
            "or replace a medical professional."
        ),
    ),
    PublicDemoSpec(
        slug="public-demo-hotel",
        public_id="demo-hotel-azurebay",
        tenant_name="Azure Bay Resort (Public Demo)",
        industry_key="hotel",
        receptionist_name="Azure Bay Resort Assistant",
        welcome_message=(
            "Welcome to Azure Bay Resort! I can share details on rooms, amenities, and policies, or "
            "help you request a reservation. What would you like to know?"
        ),
        suggested_questions=[
            "What amenities are included?",
            "Do you have airport pickup?",
            "I'd like to stay for three nights.",
        ],
        location_name="Azure Bay Resort — Front Desk",
        city="Port Serene",
        country="USA",
        working_hours=_seven_day_hours(start="00:00", end="23:59"),
        services=[
            ("Ocean-view room", "From $220/night"),
            ("Airport shuttle", "Complimentary for registered guests"),
            ("Late check-out", "Subject to availability — request at the front desk"),
        ],
        faqs=[
            (
                "What amenities are included?",
                "[FICTIONAL DEMO DATA] Azure Bay Resort includes free WiFi, a daily breakfast buffet, "
                "an outdoor pool, and a fitness center with every stay.",
            ),
            (
                "Do you have airport pickup?",
                "[FICTIONAL DEMO DATA] Yes — Azure Bay Resort offers a complimentary airport shuttle "
                "for registered guests. Share your flight details after booking and our staff will "
                "confirm a pickup time.",
            ),
        ],
        knowledge_title="About Azure Bay Resort",
        knowledge_text=(
            "[FICTIONAL DEMO DATA] Azure Bay Resort is a 60-room independent hotel in Port Serene. "
            "Every stay includes free WiFi, a daily breakfast buffet, an outdoor pool, and a fitness "
            "center. A complimentary airport shuttle is available for registered guests. Check-in is "
            "from 3pm and check-out is by 11am; early check-in and late check-out are available on "
            "request depending on availability. Multi-night reservation requests, and any request "
            "needing staff confirmation, are collected here and confirmed by our front-desk team — "
            "no reservation is guaranteed until confirmed."
        ),
    ),
    PublicDemoSpec(
        slug="public-demo-realestate",
        public_id="demo-realestate-falcon",
        tenant_name="Falcon Heights Realty (Public Demo)",
        industry_key="real_estate",
        receptionist_name="Falcon Heights Realty Assistant",
        welcome_message=(
            "Hi, I'm the virtual assistant for Falcon Heights Realty. Tell me what you're looking for "
            "— property type, budget, or location — and I can help, or arrange a site visit with an agent."
        ),
        suggested_questions=[
            "Show me available two-bedroom properties.",
            "My budget is AED 2 million.",
            "Can I schedule a site visit?",
        ],
        location_name="Falcon Heights Realty — Sales Office",
        city="Dubai",
        country="United Arab Emirates",
        working_hours=_six_day_hours(start="09:00", end="18:00"),
        services=[
            ("Buyer representation", "No cost to buyers — commission paid by seller"),
            ("Site visit scheduling", "Coordinated with a licensed agent"),
        ],
        faqs=[
            (
                "What two-bedroom properties are available?",
                "[FICTIONAL DEMO DATA] Falcon Heights Realty currently lists two-bedroom units at "
                "Marina Vista (from AED 1.8 million) and Falcon Heights Residences (from AED 2.1 "
                "million). An agent can share full listing details and arrange a site visit.",
            ),
            (
                "Can I schedule a site visit?",
                "[FICTIONAL DEMO DATA] Yes — share your preferred property and timing and we'll "
                "request a site visit with a licensed agent. Site visits are requests, not confirmed "
                "bookings, until an agent follows up.",
            ),
        ],
        knowledge_title="About Falcon Heights Realty",
        knowledge_text=(
            "[FICTIONAL DEMO DATA] Falcon Heights Realty is a residential real estate agency based "
            "in Dubai, United Arab Emirates, specializing in apartment sales and rentals. Current "
            "two-bedroom listings include Marina Vista (from AED 1.8 million) and Falcon Heights "
            "Residences (from AED 2.1 million). We capture buyer budget, location, and property "
            "preferences, and can arrange a site visit with a licensed agent — this assistant does "
            "not verify legal title, provide investment guarantees, or replace professional legal or "
            "financial advice."
        ),
    ),
]


@dataclass
class PublicDemoSeedResult:
    created: list[str]
    skipped: list[str]


def seed_public_demo_tenants(db: Session) -> PublicDemoSeedResult:
    result = PublicDemoSeedResult(created=[], skipped=[])
    tenant_repo = TenantRepository(db)

    for spec in PUBLIC_DEMO_SPECS:
        if tenant_repo.get_by_slug(spec.slug) is not None:
            result.skipped.append(spec.tenant_name)
            continue

        tenant = Tenant(name=spec.tenant_name, slug=spec.slug, timezone="UTC")
        db.add(tenant)
        db.flush()

        profile, receptionist, workflow = onboarding_service.select_industry(
            db, tenant_id=tenant.id, template_key=spec.industry_key
        )
        profile.business_name = spec.tenant_name
        update_receptionist(
            receptionist,
            ReceptionistUpdate(
                name=spec.receptionist_name,
                welcome_message=spec.welcome_message,
                suggested_questions=spec.suggested_questions,
            ),
        )
        # Must be ACTIVE before complete_onboarding — it's part of the
        # completeness bar (see onboarding_service._compute_requirements'
        # "workflow_active" check), and public demos must be reachable
        # immediately with no human ever logging in to flip them live.
        receptionist.status = ReceptionistStatus.ACTIVE

        location_service.create_location(
            db,
            tenant_id=tenant.id,
            payload=BusinessLocationCreate(
                name=spec.location_name,
                city=spec.city,
                country=spec.country,
                is_primary=True,
                working_hours=spec.working_hours,
            ),
        )

        for index, (service_name, price_note) in enumerate(spec.services):
            ServiceRepository(db, tenant.id).add(
                Service(tenant_id=tenant.id, name=service_name, price_note=price_note, display_order=index)
            )

        for question, answer in spec.faqs:
            FAQRepository(db, tenant.id).add(FAQ(tenant_id=tenant.id, question=question, answer=answer))

        source = knowledge_service.create_source(
            db, tenant_id=tenant.id, type_=KnowledgeSourceType.MANUAL, title=spec.knowledge_title
        )
        knowledge_service.create_document(
            db, tenant_id=tenant.id, source=source, title=spec.knowledge_title, raw_text=spec.knowledge_text
        )

        onboarding_service.complete_onboarding(db, tenant_id=tenant.id)

        installation = WidgetInstallation(
            tenant_id=tenant.id,
            receptionist_id=receptionist.id,
            public_id=spec.public_id,
            allowed_domains=["localhost"],
        )
        installation.status = WidgetInstallationStatus.ACTIVE
        db.add(installation)

        result.created.append(spec.tenant_name)

    db.flush()
    return result
