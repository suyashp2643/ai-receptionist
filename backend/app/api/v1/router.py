from fastapi import APIRouter

from app.api.v1 import auth, health, tenants

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(tenants.router, tags=["tenants"])
