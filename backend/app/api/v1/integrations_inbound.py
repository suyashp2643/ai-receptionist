"""The inbound integration API: lets Revenue Brain, the future AI Sales
Employee, or any other holder of a connection's inbound API key push a
narrow, closed set of events INTO this app. No dashboard JWT is ever
accepted here — auth is API-key + HMAC signature only (see
app/services/integration_inbound_service.py), and tenant scope comes
ENTIRELY from the resolved connection's own tenant_id, never from
anything in the request body or URL (there is no {tenant_id} in this
route's path at all, unlike every dashboard-facing route).

This endpoint can NEVER mutate a business record (an Enquiry, an
AppointmentRequest, a HumanHandoff) — see
integration_inbound_service.py's module docstring for the exact scope
boundary. It only durably records that an external system said
something, for a human to see in the dashboard's activity log.

Rate-limited by a hash of the presented API key (falling back to a
hashed client IP if no key was presented at all, so an attacker cannot
avoid rate limiting simply by omitting credentials) — bounds both
credential-stuffing attempts and a misbehaving legitimate caller.
"""

import hashlib

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import Settings, get_settings
from app.core.client_identity import get_client_ip, hash_client_ip
from app.core.rate_limit import RateLimiter, get_rate_limiter
from app.schemas.integration_inbound import InboundEventSubmitRequest, InboundEventSubmitResponse
from app.services.integration_inbound_service import InboundAuthError, InboundConflictError, process_inbound_event

router = APIRouter(prefix="/integrations/inbound")

_RATE_LIMIT = 30
_RATE_WINDOW_SECONDS = 60


def _rate_limit_key(request: Request, *, raw_api_key: str | None, settings: Settings) -> str:
    if raw_api_key:
        return f"inbound:key:{hashlib.sha256(raw_api_key.encode('utf-8')).hexdigest()}"
    ip = get_client_ip(request, trust_proxy_headers=settings.trust_proxy_headers)
    return f"inbound:ip:{hash_client_ip(ip)}"


@router.post("/events", response_model=InboundEventSubmitResponse)
async def submit_inbound_event(
    request: Request,
    payload: InboundEventSubmitRequest,
    x_integration_api_key: str | None = Header(default=None),
    x_integration_signature: str | None = Header(default=None),
    x_integration_timestamp: str | None = Header(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> InboundEventSubmitResponse:
    key = _rate_limit_key(request, raw_api_key=x_integration_api_key, settings=settings)
    result = limiter.check(key, limit=_RATE_LIMIT, window_seconds=_RATE_WINDOW_SECONDS)
    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again shortly.",
            headers={"Retry-After": str(result.retry_after_seconds)},
        )

    raw_body = await request.body()
    try:
        outcome = process_inbound_event(
            db,
            raw_api_key=x_integration_api_key,
            signature=x_integration_signature,
            timestamp=x_integration_timestamp,
            raw_body=raw_body,
            request=payload,
            settings=settings,
        )
    except InboundAuthError as exc:
        # Deliberately the exact same generic message and status for every
        # possible auth failure reason — see InboundAuthError's docstring.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.") from exc
    except InboundConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    db.commit()
    return InboundEventSubmitResponse(status=outcome.status, external_event_id=payload.external_event_id)
