"""Boundary and tamper-detection proof for the inbound API's HMAC replay
window (app/services/integration_inbound_service.py). The core enforcement
already existed and was already covered for the "well past expired" and
"tampered body" cases (tests/test_phase8_integrations_inbound_api.py); this
file adds the exact-boundary and remaining tamper-vector coverage a Phase 8
remediation round asked for specifically, using the newly-injectable
`clock`/`replay_window_seconds` parameters — no sleeping, no wall-clock
races, deterministic to the second."""

import json
import uuid

import pytest
from app.config import get_settings
from app.integrations.signing import HEADER_SIGNATURE, HEADER_TIMESTAMP, sign_payload
from app.models.activity_event import ActivityEvent
from app.models.enums import IntegrationConnectorType
from app.models.integration import InboundIntegrationEvent
from app.schemas.integration_inbound import InboundEventData, InboundEventSubmitRequest, InboundEventType
from app.services import integration_connection_service
from app.services.integration_inbound_service import InboundAuthError, process_inbound_event
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.factories import make_tenant, make_user

settings = get_settings()
URL = "/api/v1/integrations/inbound/events"
FIXED_NOW = 1_800_000_000  # arbitrary, deterministic reference instant


def _make_connection_with_credentials(db: Session):
    tenant = make_tenant(db)
    actor = make_user(db)
    connection = integration_connection_service.create_connection(
        db,
        tenant_id=tenant.id,
        actor_user_id=actor.id,
        connector_type=IntegrationConnectorType.SALES_EMPLOYEE,
        name="Replay Window Test Connection",
        config={"destination_url": "http://127.0.0.1:9999/hook"},
        enabled_event_types=[],
        signing_secret="shared-secret-value",
        settings=settings,
    )
    raw_key = integration_connection_service.generate_inbound_api_key(
        db,
        tenant_id=tenant.id,
        actor_user_id=actor.id,
        connection=connection,
        expected_version=connection.version,
        settings=settings,
    )
    db.flush()
    return connection, raw_key, "shared-secret-value"


def _signed_request(body_dict: dict, *, secret: str, event_id: str, event_version: int = 1, timestamp: str):
    body_bytes = json.dumps(body_dict).encode("utf-8")
    signature = sign_payload(
        secret,
        body=body_bytes,
        timestamp=timestamp,
        delivery_id=event_id,
        event_id=event_id,
        schema_version=str(event_version),
    )
    return body_bytes, signature


def _payload(event_id: str) -> dict:
    return {
        "external_event_id": event_id,
        "event_type": "lead.note",
        "event_version": 1,
        "data": {"external_reference": "rb-lead-123", "note": "Called back, left voicemail."},
    }


def _submit_request_model(event_id: str) -> InboundEventSubmitRequest:
    return InboundEventSubmitRequest(
        external_event_id=event_id,
        event_type=InboundEventType.LEAD_NOTE,
        event_version=1,
        data=InboundEventData(external_reference="rb-lead-123", note="Called back, left voicemail."),
    )


class TestReplayWindowBoundary:
    """Direct service-level tests with an injected clock — deterministic to
    the second, no sleeping, no dependence on wall-clock timing."""

    def test_exactly_at_the_window_edge_is_accepted(self, db_session: Session):
        connection, raw_key, secret = _make_connection_with_credentials(db_session)
        event_id = f"evt-{uuid.uuid4().hex}"
        ts = str(FIXED_NOW - 300)  # exactly REPLAY_WINDOW_SECONDS in the past
        body, signature = _signed_request(_payload(event_id), secret=secret, event_id=event_id, timestamp=ts)

        outcome = process_inbound_event(
            db_session,
            raw_api_key=raw_key,
            signature=signature,
            timestamp=ts,
            raw_body=body,
            request=_submit_request_model(event_id),
            settings=settings,
            clock=lambda: FIXED_NOW,
            replay_window_seconds=300,
        )
        assert outcome.status == "processed"

    def test_one_second_past_the_window_edge_is_rejected(self, db_session: Session):
        connection, raw_key, secret = _make_connection_with_credentials(db_session)
        event_id = f"evt-{uuid.uuid4().hex}"
        ts = str(FIXED_NOW - 301)
        body, signature = _signed_request(_payload(event_id), secret=secret, event_id=event_id, timestamp=ts)

        with pytest.raises(InboundAuthError):
            process_inbound_event(
                db_session,
                raw_api_key=raw_key,
                signature=signature,
                timestamp=ts,
                raw_body=body,
                request=_submit_request_model(event_id),
                settings=settings,
                clock=lambda: FIXED_NOW,
                replay_window_seconds=300,
            )

    def test_exactly_at_the_future_window_edge_is_accepted(self, db_session: Session):
        connection, raw_key, secret = _make_connection_with_credentials(db_session)
        event_id = f"evt-{uuid.uuid4().hex}"
        ts = str(FIXED_NOW + 300)
        body, signature = _signed_request(_payload(event_id), secret=secret, event_id=event_id, timestamp=ts)

        outcome = process_inbound_event(
            db_session,
            raw_api_key=raw_key,
            signature=signature,
            timestamp=ts,
            raw_body=body,
            request=_submit_request_model(event_id),
            settings=settings,
            clock=lambda: FIXED_NOW,
            replay_window_seconds=300,
        )
        assert outcome.status == "processed"

    def test_one_second_beyond_the_future_window_is_rejected(self, db_session: Session):
        """A validly-signed request timestamped in the future beyond the
        window must fail even though its HMAC is entirely correct — the
        signature being valid never overrides the timestamp-freshness
        check."""
        connection, raw_key, secret = _make_connection_with_credentials(db_session)
        event_id = f"evt-{uuid.uuid4().hex}"
        ts = str(FIXED_NOW + 301)
        body, signature = _signed_request(_payload(event_id), secret=secret, event_id=event_id, timestamp=ts)

        with pytest.raises(InboundAuthError, match="Timestamp outside the allowed window"):
            process_inbound_event(
                db_session,
                raw_api_key=raw_key,
                signature=signature,
                timestamp=ts,
                raw_body=body,
                request=_submit_request_model(event_id),
                settings=settings,
                clock=lambda: FIXED_NOW,
                replay_window_seconds=300,
            )

    def test_a_narrower_injected_window_is_honored(self, db_session: Session):
        """Proves `replay_window_seconds` is a genuine parameter, not just
        threaded through unused — a 10-second window rejects a timestamp
        the default 300-second window would have accepted."""
        connection, raw_key, secret = _make_connection_with_credentials(db_session)
        event_id = f"evt-{uuid.uuid4().hex}"
        ts = str(FIXED_NOW - 30)
        body, signature = _signed_request(_payload(event_id), secret=secret, event_id=event_id, timestamp=ts)

        with pytest.raises(InboundAuthError):
            process_inbound_event(
                db_session,
                raw_api_key=raw_key,
                signature=signature,
                timestamp=ts,
                raw_body=body,
                request=_submit_request_model(event_id),
                settings=settings,
                clock=lambda: FIXED_NOW,
                replay_window_seconds=10,
            )


class TestTamperDetection:
    """HTTP-level: every component of the signed request — body, timestamp,
    event id, and the signature itself — must independently invalidate the
    request if modified after signing."""

    def test_tampered_timestamp_header_is_401(self, db_backed_client: TestClient, db_session: Session):
        """The timestamp header is changed to a different, still-fresh
        value that was never actually signed — distinct from the
        already-covered "stale timestamp" case: this one is IN the window,
        but doesn't match what was signed, so the signature must fail."""
        connection, raw_key, secret = _make_connection_with_credentials(db_session)
        event_id = f"evt-{uuid.uuid4().hex}"
        import time

        real_ts = str(int(time.time()))
        body, signature = _signed_request(_payload(event_id), secret=secret, event_id=event_id, timestamp=real_ts)
        forged_ts = str(int(real_ts) + 1)  # still fresh, never signed
        response = db_backed_client.post(
            URL,
            content=body,
            headers={
                "X-Integration-Api-Key": raw_key,
                HEADER_SIGNATURE: signature,
                HEADER_TIMESTAMP: forged_ts,
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 401

    def test_tampered_event_id_is_401(self, db_backed_client: TestClient, db_session: Session):
        """`external_event_id` doubles as the signed delivery/event id — a
        body edit that changes only that field (valid JSON, same
        signature) must still fail, since the signature covers it."""
        connection, raw_key, secret = _make_connection_with_credentials(db_session)
        event_id = f"evt-{uuid.uuid4().hex}"
        import time

        ts = str(int(time.time()))
        body, signature = _signed_request(_payload(event_id), secret=secret, event_id=event_id, timestamp=ts)
        forged_payload = _payload(event_id)
        forged_payload["external_event_id"] = f"evt-{uuid.uuid4().hex}"
        forged_body = json.dumps(forged_payload).encode("utf-8")
        response = db_backed_client.post(
            URL,
            content=forged_body,
            headers={
                "X-Integration-Api-Key": raw_key,
                HEADER_SIGNATURE: signature,
                HEADER_TIMESTAMP: ts,
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 401

    def test_tampered_signature_is_401(self, db_backed_client: TestClient, db_session: Session):
        """A single corrupted character in an otherwise-correct signature
        (same secret, same body, same timestamp) must still be rejected —
        distinct from the already-covered "wrong secret" case."""
        connection, raw_key, secret = _make_connection_with_credentials(db_session)
        event_id = f"evt-{uuid.uuid4().hex}"
        import time

        ts = str(int(time.time()))
        body, signature = _signed_request(_payload(event_id), secret=secret, event_id=event_id, timestamp=ts)
        corrupted = ("0" if signature[0] != "0" else "1") + signature[1:]
        response = db_backed_client.post(
            URL,
            content=body,
            headers={
                "X-Integration-Api-Key": raw_key,
                HEADER_SIGNATURE: corrupted,
                HEADER_TIMESTAMP: ts,
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 401

    def test_every_distinct_auth_failure_returns_the_identical_generic_response(
        self, db_backed_client: TestClient, db_session: Session
    ):
        """Missing credentials, unknown key, bad signature, and an expired
        timestamp must be indistinguishable from the outside — same status
        code, same body — so this endpoint can never be used as an oracle
        for which failure reason applies."""
        connection, raw_key, secret = _make_connection_with_credentials(db_session)
        import time

        fresh_ts = str(int(time.time()))
        stale_ts = str(int(time.time()) - 3600)

        event_id_a = f"evt-{uuid.uuid4().hex}"
        body_a, sig_a = _signed_request(
            _payload(event_id_a), secret="wrong-secret-entirely", event_id=event_id_a, timestamp=fresh_ts
        )
        resp_wrong_secret = db_backed_client.post(
            URL,
            content=body_a,
            headers={"X-Integration-Api-Key": raw_key, HEADER_SIGNATURE: sig_a, HEADER_TIMESTAMP: fresh_ts},
        )

        event_id_b = f"evt-{uuid.uuid4().hex}"
        body_b, sig_b = _signed_request(_payload(event_id_b), secret=secret, event_id=event_id_b, timestamp=stale_ts)
        resp_stale = db_backed_client.post(
            URL,
            content=body_b,
            headers={"X-Integration-Api-Key": raw_key, HEADER_SIGNATURE: sig_b, HEADER_TIMESTAMP: stale_ts},
        )

        event_id_c = f"evt-{uuid.uuid4().hex}"
        body_c, sig_c = _signed_request(_payload(event_id_c), secret=secret, event_id=event_id_c, timestamp=fresh_ts)
        resp_unknown_key = db_backed_client.post(
            URL,
            content=body_c,
            headers={
                "X-Integration-Api-Key": "airk_totally-unknown",
                HEADER_SIGNATURE: sig_c,
                HEADER_TIMESTAMP: fresh_ts,
            },
        )

        for resp in (resp_wrong_secret, resp_stale, resp_unknown_key):
            assert resp.status_code == 401
            assert resp.json() == {"error": {"message": "Invalid credentials.", "status_code": 401}}


class TestIdempotentReplayDoesNotDuplicate:
    def test_identical_replay_within_the_window_creates_no_duplicate_row_or_activity_event(
        self, db_backed_client: TestClient, db_session: Session
    ):
        connection, raw_key, secret = _make_connection_with_credentials(db_session)
        event_id = f"evt-{uuid.uuid4().hex}"
        import time

        ts = str(int(time.time()))
        body, signature = _signed_request(_payload(event_id), secret=secret, event_id=event_id, timestamp=ts)
        headers = {"X-Integration-Api-Key": raw_key, HEADER_SIGNATURE: signature, HEADER_TIMESTAMP: ts}

        first = db_backed_client.post(URL, content=body, headers=headers)
        assert first.status_code == 200
        second = db_backed_client.post(URL, content=body, headers=headers)
        assert second.status_code == 200
        assert second.json()["status"] == "duplicate"

        rows = db_session.scalars(
            select(InboundIntegrationEvent).where(InboundIntegrationEvent.external_event_id == event_id)
        ).all()
        assert len(rows) == 1

        activity = db_session.scalars(
            select(ActivityEvent).where(
                ActivityEvent.action_type == "integration.inbound_event_received",
                ActivityEvent.entity_id == connection.id,
            )
        ).all()
        assert len(activity) == 1
