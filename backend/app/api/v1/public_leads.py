"""Public marketing-site lead capture (Phase 7) — the only route in this
router, deliberately: there is no read/list endpoint. Exposing submitted
leads through any public API, or forcing them into a synthetic "platform"
tenant just to reuse TenantContext, was explicitly rejected in favor of a
global model an operator queries directly during local development (see
docs/local-development.md and docs/security.md)."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import Settings, get_settings
from app.core.client_identity import get_client_ip, hash_client_ip
from app.core.rate_limit import RateLimiter, get_rate_limiter
from app.schemas.public_lead import PublicLeadCreateRequest, PublicLeadSubmitResponse
from app.services.public_lead_service import create_lead

router = APIRouter()

_RATE_LIMIT_ACTION = "public_lead_submit"
_RATE_LIMIT_MAX = 5
_RATE_LIMIT_WINDOW_SECONDS = 3600


def _rate_limit(
    request: Request,
    settings: Settings = Depends(get_settings),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> None:
    """IP-only-keyed variant of app.api.widget_deps.rate_limit — this route
    has no installation to key on. Same InMemoryRateLimiter, same
    single-process limitation documented in app/core/rate_limit.py."""
    ip = get_client_ip(request, trust_proxy_headers=settings.trust_proxy_headers)
    key = f"{_RATE_LIMIT_ACTION}:{hash_client_ip(ip)}"
    result = limiter.check(key, limit=_RATE_LIMIT_MAX, window_seconds=_RATE_LIMIT_WINDOW_SECONDS)
    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again shortly.",
            headers={"Retry-After": str(result.retry_after_seconds)},
        )


@router.post(
    "/public/leads",
    response_model=PublicLeadSubmitResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_rate_limit)],
)
def submit_public_lead(
    payload: PublicLeadCreateRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> PublicLeadSubmitResponse:
    ip = get_client_ip(request, trust_proxy_headers=settings.trust_proxy_headers)
    create_lead(db, payload=payload, ip_hash=hash_client_ip(ip))
    db.commit()
    # Identical response whether stored or silently dropped as a honeypot
    # hit — see PublicLeadSubmitResponse's docstring.
    return PublicLeadSubmitResponse()
