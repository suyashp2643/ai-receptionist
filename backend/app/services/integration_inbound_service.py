"""Authenticates and processes one inbound integration event. This is the
ONE place credentials from an external caller (Revenue Brain, the future
AI Sales Employee, or any other holder of a connection's inbound API key)
are verified — app/api/v1/integrations_inbound.py's route stays thin and
never touches crypto directly.

No arbitrary mutation: processing an inbound event NEVER calls into
enquiry_service/appointment_request_service/human_handoff_service to
change a business record's state. It only durably records the event
(InboundIntegrationEvent, append-only, and an ActivityEvent so a dashboard
user sees it) — a deliberate Phase 8 scope boundary, not an oversight; see
this module's own docstring in app/schemas/integration_inbound.py. A
future phase that wants inbound events to drive a real transition should
route through the existing service-layer transition functions (which
already enforce the valid-transition graph and record their own activity
events) rather than bypassing them here.

Auth failures are reported as a single generic error regardless of *why*
authentication failed (key not found, no secret configured, bad
signature, expired timestamp) — never distinguishable by an external
caller, which is what keeps this endpoint from being an oracle for
enumerating valid API keys.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import Settings
from app.core.crypto import SecretDecryptionError, decrypt_secret, hash_api_key
from app.integrations.signing import REPLAY_WINDOW_SECONDS, verify_signature
from app.models.enums import InboundEventStatus
from app.models.integration import InboundIntegrationEvent, IntegrationConnection
from app.repositories.integration import InboundIntegrationEventRepository, find_connection_by_inbound_api_key_hash
from app.schemas.integration_inbound import InboundEventSubmitRequest
from app.services import activity_service


class InboundAuthError(Exception):
    """Raised for any authentication failure — see this module's docstring
    for why the API route must map every instance of this to the exact
    same generic 401, never a more specific message."""


class InboundConflictError(Exception):
    """Raised when `external_event_id` was already processed with a
    DIFFERENT payload — a genuine replay (same id, same payload) is not an
    error; see the idempotency check below."""


@dataclass(frozen=True)
class InboundOutcome:
    status: str  # "processed" | "duplicate"


def _authenticate(
    db: Session,
    *,
    raw_api_key: str | None,
    signature: str | None,
    timestamp: str | None,
    raw_body: bytes,
    event_id_for_signature: str,
    event_version: int,
    settings: Settings,
    clock: Callable[[], int] = lambda: int(time.time()),
    replay_window_seconds: int = REPLAY_WINDOW_SECONDS,
) -> IntegrationConnection:
    if not raw_api_key or not signature or not timestamp:
        raise InboundAuthError("Missing credentials.")

    try:
        timestamp_int = int(timestamp)
    except ValueError as exc:
        raise InboundAuthError("Invalid timestamp.") from exc
    # `abs(...)` deliberately rejects a timestamp too far in the future the
    # same way it rejects one too far in the past — a signed request dated
    # ahead of "now" is exactly as suspect as a stale one (e.g. a clock-skew
    # attack, or a captured request replayed with a forged future
    # timestamp), and neither should get a grace period the other doesn't.
    # `clock`/`replay_window_seconds` are injectable so tests can assert the
    # exact boundary deterministically — no sleeping, no wall-clock races.
    if abs(clock() - timestamp_int) > replay_window_seconds:
        raise InboundAuthError("Timestamp outside the allowed window.")

    connection = find_connection_by_inbound_api_key_hash(db, hash_api_key(raw_api_key))
    if connection is None or not connection.signing_secret_ciphertext:
        raise InboundAuthError("Invalid credentials.")

    try:
        secret = decrypt_secret(
            connection.signing_secret_ciphertext,
            key_version=connection.signing_secret_key_version or 0,
            settings=settings,
        )
    except SecretDecryptionError as exc:
        raise InboundAuthError("Invalid credentials.") from exc

    ok = verify_signature(
        secret,
        signature=signature,
        body=raw_body,
        timestamp=timestamp,
        delivery_id=event_id_for_signature,
        event_id=event_id_for_signature,
        schema_version=str(event_version),
    )
    if not ok:
        raise InboundAuthError("Invalid signature.")

    return connection


def process_inbound_event(
    db: Session,
    *,
    raw_api_key: str | None,
    signature: str | None,
    timestamp: str | None,
    raw_body: bytes,
    request: InboundEventSubmitRequest,
    settings: Settings,
    clock: Callable[[], int] = lambda: int(time.time()),
    replay_window_seconds: int = REPLAY_WINDOW_SECONDS,
) -> InboundOutcome:
    connection = _authenticate(
        db,
        raw_api_key=raw_api_key,
        signature=signature,
        timestamp=timestamp,
        raw_body=raw_body,
        event_id_for_signature=request.external_event_id,
        event_version=request.event_version,
        settings=settings,
        clock=clock,
        replay_window_seconds=replay_window_seconds,
    )

    payload_hash = hashlib.sha256(raw_body).hexdigest()
    repo = InboundIntegrationEventRepository(db, connection.tenant_id)
    existing = repo.get_by_external_id(connection_id=connection.id, external_event_id=request.external_event_id)
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise InboundConflictError("external_event_id was already processed with a different payload.")
        return InboundOutcome(status="duplicate")

    row = InboundIntegrationEvent(
        tenant_id=connection.tenant_id,
        connection_id=connection.id,
        external_event_id=request.external_event_id,
        event_type=request.event_type.value,
        event_version=request.event_version,
        status=InboundEventStatus.PROCESSED,
        payload_hash=payload_hash,
    )
    db.add(row)

    connection.last_inbound_event_at = datetime.now(UTC)

    activity_service.record(
        db,
        tenant_id=connection.tenant_id,
        actor_user_id=None,
        action_type="integration.inbound_event_received",
        entity_type="integration_connection",
        entity_id=connection.id,
        metadata={"event_type": request.event_type.value, "external_reference": request.data.external_reference},
    )
    db.flush()
    return InboundOutcome(status="processed")
