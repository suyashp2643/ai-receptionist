"""Development-only demo data: three FICTIONAL businesses used to showcase
the onboarding flow. Never runs automatically, never used in production,
never creates fake metrics/testimonials — just a realistic-looking starting
point for manual local testing.

Each demo user gets a freshly generated random password, printed once to
the console by the calling script and never stored anywhere else (not in
this file, not in any tracked document).
"""

import secrets
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import Settings
from app.core.normalization import normalize_email
from app.models.enums import KnowledgeSourceType
from app.models.faq import FAQ
from app.models.service import Service
from app.repositories.faq import FAQRepository
from app.repositories.service import ServiceRepository
from app.repositories.user import UserRepository
from app.schemas.auth import RegisterRequest
from app.schemas.business_location import BusinessLocationCreate
from app.schemas.receptionist import ReceptionistUpdate
from app.services import knowledge_service, location_service, onboarding_service
from app.services.auth_service import register_user
from app.services.receptionist_service import update_receptionist


@dataclass
class DemoTenantSpec:
    email: str
    display_name: str
    workspace_name: str
    business_name: str
    short_description: str
    industry_key: str
    location_name: str
    city: str
    country: str
    services: list[tuple[str, str]]  # (name, price_note)
    faq: tuple[str, str]
    knowledge_title: str
    knowledge_text: str


DEMO_SPECS: list[DemoTenantSpec] = [
    DemoTenantSpec(
        email="demo-realestate@example.com",
        display_name="Jordan Rivera",
        workspace_name="Meridian Realty Group",
        business_name="Meridian Realty Group",
        short_description="[FICTIONAL DEMO DATA] A residential and commercial real estate agency.",
        industry_key="real_estate",
        location_name="Meridian Realty — Downtown Office",
        city="Springfield",
        country="USA",
        services=[
            ("Buyer representation", "No cost to buyers — commission paid by seller"),
            ("Property management", "Starting at 8% of monthly rent"),
        ],
        faq=(
            "Do you handle both residential and commercial properties?",
            "[FICTIONAL DEMO DATA] Yes, Meridian Realty Group handles both residential and "
            "commercial listings across the Springfield metro area.",
        ),
        knowledge_title="About Meridian Realty Group",
        knowledge_text=(
            "[FICTIONAL DEMO DATA] Meridian Realty Group is a locally owned real estate agency "
            "founded in 2015, serving buyers, renters, and investors across the Springfield metro "
            "area. Our agents specialize in residential sales, rentals, and small commercial "
            "properties. We are open Monday through Saturday and offer virtual tours on request."
        ),
    ),
    DemoTenantSpec(
        email="demo-clinic@example.com",
        display_name="Dr. Amara Osei",
        workspace_name="Brightsmile Dental Clinic",
        business_name="Brightsmile Dental Clinic",
        short_description="[FICTIONAL DEMO DATA] A family dental clinic offering general and cosmetic dentistry.",
        industry_key="clinic",
        location_name="Brightsmile Dental — Main Clinic",
        city="Riverton",
        country="USA",
        services=[
            ("Routine cleaning and checkup", "Covered by most insurance plans"),
            ("Teeth whitening", "Starting at $250"),
        ],
        faq=(
            "Are you accepting new patients?",
            "[FICTIONAL DEMO DATA] Yes, Brightsmile Dental Clinic is currently accepting new patients of all ages.",
        ),
        knowledge_title="About Brightsmile Dental Clinic",
        knowledge_text=(
            "[FICTIONAL DEMO DATA] Brightsmile Dental Clinic is a family dental practice in "
            "Riverton offering general checkups, cleanings, cosmetic dentistry, and emergency "
            "appointments. Our administrative team can help schedule appointments and answer "
            "questions about insurance and office policies. For any dental emergency or medical "
            "concern, please contact the clinic directly or seek emergency care."
        ),
    ),
    DemoTenantSpec(
        email="demo-hotel@example.com",
        display_name="Priya Kapoor",
        workspace_name="The Wren Boutique Hotel",
        business_name="The Wren Boutique Hotel",
        short_description="[FICTIONAL DEMO DATA] A 24-room boutique hotel in the historic district.",
        industry_key="hotel",
        location_name="The Wren Boutique Hotel",
        city="Ashford",
        country="USA",
        services=[
            ("Standard room", "From $180/night"),
            ("Airport shuttle", "Complimentary for guests"),
        ],
        faq=(
            "Is breakfast included?",
            "[FICTIONAL DEMO DATA] Yes, a complimentary continental breakfast is included "
            "with every stay at The Wren Boutique Hotel.",
        ),
        knowledge_title="About The Wren Boutique Hotel",
        knowledge_text=(
            "[FICTIONAL DEMO DATA] The Wren Boutique Hotel is a 24-room independent hotel located "
            "in the historic district of Ashford. We offer complimentary breakfast, an airport "
            "shuttle, and a small on-site cafe. Check-in is from 3pm and check-out is by 11am, "
            "with early check-in available on request depending on availability."
        ),
    ),
]


@dataclass
class DemoSeedResult:
    created: list[str]
    skipped: list[str]
    generated_credentials: list[tuple[str, str]]  # (email, one-time password) — never persisted


def seed_demo_tenants(db: Session, settings: Settings) -> DemoSeedResult:
    result = DemoSeedResult(created=[], skipped=[], generated_credentials=[])
    user_repo = UserRepository(db)

    for spec in DEMO_SPECS:
        normalized_email = normalize_email(spec.email)
        if user_repo.get_by_normalized_email(normalized_email) is not None:
            result.skipped.append(spec.workspace_name)
            continue

        password = secrets.token_urlsafe(18)
        register_request = RegisterRequest(
            display_name=spec.display_name,
            email=spec.email,
            password=password,
            workspace_name=spec.workspace_name,
            timezone="UTC",
        )
        user, tenant, _member, _session = register_user(db, settings, register_request)

        profile, receptionist, _workflow = onboarding_service.select_industry(
            db, tenant_id=tenant.id, template_key=spec.industry_key
        )
        profile.business_name = spec.business_name
        profile.short_description = spec.short_description

        update_receptionist(receptionist, ReceptionistUpdate(name=f"{spec.workspace_name} Assistant"))

        location_service.create_location(
            db,
            tenant_id=tenant.id,
            payload=BusinessLocationCreate(
                name=spec.location_name, city=spec.city, country=spec.country, is_primary=True
            ),
        )

        for index, (service_name, price_note) in enumerate(spec.services):
            ServiceRepository(db, tenant.id).add(
                Service(
                    tenant_id=tenant.id,
                    name=service_name,
                    price_note=price_note,
                    display_order=index,
                )
            )

        question, answer = spec.faq
        FAQRepository(db, tenant.id).add(FAQ(tenant_id=tenant.id, question=question, answer=answer))

        source = knowledge_service.create_source(
            db, tenant_id=tenant.id, type_=KnowledgeSourceType.MANUAL, title=spec.knowledge_title
        )
        knowledge_service.create_document(
            db,
            tenant_id=tenant.id,
            source=source,
            title=spec.knowledge_title,
            raw_text=spec.knowledge_text,
        )

        onboarding_service.complete_onboarding(db, tenant_id=tenant.id)

        result.created.append(spec.workspace_name)
        result.generated_credentials.append((spec.email, password))

    db.flush()
    return result
