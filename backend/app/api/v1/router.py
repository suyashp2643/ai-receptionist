from fastapi import APIRouter

from app.api.v1 import (
    auth,
    conversations,
    faqs,
    health,
    industry_templates,
    knowledge,
    locations,
    onboarding,
    receptionists,
    services,
    tenants,
    timezones,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(timezones.router, tags=["timezones"])
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(tenants.router, tags=["tenants"])
api_router.include_router(industry_templates.router, tags=["industry-templates"])
api_router.include_router(onboarding.router, tags=["onboarding"])
api_router.include_router(receptionists.router, tags=["receptionists"])
api_router.include_router(locations.router, tags=["locations"])
api_router.include_router(services.router, tags=["services"])
api_router.include_router(faqs.router, tags=["faqs"])
api_router.include_router(knowledge.router, tags=["knowledge"])
api_router.include_router(conversations.router, tags=["conversations"])
