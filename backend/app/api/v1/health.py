from fastapi import APIRouter

from app.config import get_settings
from app.db.session import check_database_connection
from app.schemas.health import DatabaseHealth, HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Reports service + database health. Never raises on DB unavailability."""
    settings = get_settings()
    db_health = check_database_connection()
    overall_status = "ok" if db_health["status"] in ("ok", "not_configured") else "degraded"
    return HealthResponse(
        status=overall_status,
        service=settings.app_name,
        environment=settings.environment,
        database=DatabaseHealth(**db_health),
    )
