from fastapi import APIRouter

from app.core.timezones import SORTED_TIMEZONES
from app.schemas.timezone import TimezoneListResponse

router = APIRouter()


@router.get("/timezones", response_model=TimezoneListResponse)
def list_timezones() -> TimezoneListResponse:
    """Public and unauthenticated — the registration form needs a
    backend-valid timezone list before any user or session exists. This is
    the same `zoneinfo.available_timezones()` set every timezone field is
    validated against, so anything the frontend renders from here is
    guaranteed acceptable on submit."""
    return TimezoneListResponse(timezones=SORTED_TIMEZONES)
