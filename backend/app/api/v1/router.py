from fastapi import APIRouter

from app.api.v1 import (
    activity,
    analytics,
    auth,
    conversations,
    dashboard_conversations,
    dashboard_records,
    exports,
    faqs,
    health,
    industry_templates,
    knowledge,
    locations,
    notes,
    onboarding,
    receptionists,
    services,
    tenants,
    timezones,
    widget_installations,
    widget_public,
    widget_records,
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
api_router.include_router(widget_installations.router, tags=["widget-installations"])
api_router.include_router(widget_records.router, tags=["widget-records"])
api_router.include_router(widget_public.router, tags=["widget-public"])
api_router.include_router(analytics.router, tags=["analytics"])
api_router.include_router(dashboard_conversations.router, tags=["dashboard-conversations"])
api_router.include_router(dashboard_records.router, tags=["dashboard-records"])
api_router.include_router(notes.router, tags=["notes"])
api_router.include_router(activity.router, tags=["activity"])
api_router.include_router(exports.router, tags=["exports"])
