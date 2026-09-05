"""Inbound integration API tests. Every signed request is built the same
way a real caller (Revenue Brain, etc.) would: hash the raw JSON body,
sign it with the connection's own shared secret via
app.integrations.signing, and attach the resulting headers — never a
shortcut that bypasses what the route actually verifies."""

import json
import time
import uuid

from app.config import get_settings
from app.integrations.signing import HEADER_SIGNATURE, HEADER_TIMESTAMP, sign_payload
from app.models.appointment_request import AppointmentRequest
from app.models.enquiry import Enquiry
from app.models.enums import IntegrationConnectorType
from app.models.human_handoff import HumanHandoff
from app.services import integration_connection_service
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.factories import make_tenant, make_user

settings = get_settings()

URL = "/api/v1/integrations/inbound/events"


def _make_connection_with_credentials(db: Session, *, tenant=None):
    tenant = tenant or make_tenant(db)
    actor = make_user(db)
    connection = integration_connection_service.create_connection(
        db,
        tenant_id=tenant.id,
        actor_user_id=actor.id,
        connector_type=IntegrationConnectorType.SALES_EMPLOYEE,
        name="Inbound Test Connection",
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


def _signed_request(
    body_dict: dict, *, api_key: str, secret: str, event_id: str, event_version: int = 1, timestamp: str | None = None
):
    body_bytes = json.dumps(body_dict).encode("utf-8")
    ts = timestamp or str(int(time.time()))
    signature = sign_payload(
        secret,
        body=body_bytes,
        timestamp=ts,
        delivery_id=event_id,
        event_id=event_id,
        schema_version=str(event_version),
    )
    headers = {
        "X-Integration-Api-Key": api_key,
        HEADER_SIGNATURE: signature,
        HEADER_TIMESTAMP: ts,
        "Content-Type": "application/json",
    }
    return body_bytes, headers


def _payload(event_id: str) -> dict:
    return {
        "external_event_id": event_id,
        "event_type": "lead.note",
        "event_version": 1,
        "data": {"external_reference": "rb-lead-123", "note": "Called back, left voicemail."},
    }


class TestAuthentication:
    def test_valid_signature_is_accepted(self, db_backed_client: TestClient, db_session: Session):
        connection, raw_key, secret = _make_connection_with_credentials(db_session)
        event_id = f"evt-{uuid.uuid4().hex}"
        body, headers = _signed_request(_payload(event_id), api_key=raw_key, secret=secret, event_id=event_id)

        response = db_backed_client.post(URL, content=body, headers=headers)
        assert response.status_code == 200
        assert response.json() == {"status": "processed", "external_event_id": event_id}

    def test_missing_headers_is_401(self, db_backed_client: TestClient, db_session: Session):
        _connection, _raw_key, _secret = _make_connection_with_credentials(db_session)
        event_id = f"evt-{uuid.uuid4().hex}"
        response = db_backed_client.post(URL, json=_payload(event_id))
        assert response.status_code == 401

    def test_unknown_api_key_is_401(self, db_backed_client: TestClient, db_session: Session):
        _make_connection_with_credentials(db_session)
        event_id = f"evt-{uuid.uuid4().hex}"
        body, headers = _signed_request(
            _payload(event_id), api_key="airk_totally-made-up-key", secret="whatever", event_id=event_id
        )
        response = db_backed_client.post(URL, content=body, headers=headers)
        assert response.status_code == 401

    def test_wrong_secret_signature_is_401(self, db_backed_client: TestClient, db_session: Session):
        _connection, raw_key, _secret = _make_connection_with_credentials(db_session)
        event_id = f"evt-{uuid.uuid4().hex}"
        body, headers = _signed_request(_payload(event_id), api_key=raw_key, secret="wrong-secret", event_id=event_id)
        response = db_backed_client.post(URL, content=body, headers=headers)
        assert response.status_code == 401

    def test_tampered_body_after_signing_is_401(self, db_backed_client: TestClient, db_session: Session):
        connection, raw_key, secret = _make_connection_with_credentials(db_session)
        event_id = f"evt-{uuid.uuid4().hex}"
        body, headers = _signed_request(_payload(event_id), api_key=raw_key, secret=secret, event_id=event_id)
        tampered = body.replace(b"Called back", b"XXXXXXXXXXX")
        response = db_backed_client.post(URL, content=tampered, headers=headers)
        assert response.status_code == 401

    def test_expired_timestamp_is_401(self, db_backed_client: TestClient, db_session: Session):
        connection, raw_key, secret = _make_connection_with_credentials(db_session)
        event_id = f"evt-{uuid.uuid4().hex}"
        stale_timestamp = str(int(time.time()) - 3600)
        body, headers = _signed_request(
            _payload(event_id), api_key=raw_key, secret=secret, event_id=event_id, timestamp=stale_timestamp
        )
        response = db_backed_client.post(URL, content=body, headers=headers)
        assert response.status_code == 401

    def test_unrecognized_event_type_is_422(self, db_backed_client: TestClient, db_session: Session):
        connection, raw_key, secret = _make_connection_with_credentials(db_session)
        event_id = f"evt-{uuid.uuid4().hex}"
        payload = _payload(event_id)
        payload["event_type"] = "not.a.real.event"
        body, headers = _signed_request(payload, api_key=raw_key, secret=secret, event_id=event_id)
        response = db_backed_client.post(URL, content=body, headers=headers)
        assert response.status_code == 422


class TestIdempotency:
    def test_identical_replay_is_a_harmless_duplicate(self, db_backed_client: TestClient, db_session: Session):
        connection, raw_key, secret = _make_connection_with_credentials(db_session)
        event_id = f"evt-{uuid.uuid4().hex}"
        body, headers = _signed_request(_payload(event_id), api_key=raw_key, secret=secret, event_id=event_id)

        first = db_backed_client.post(URL, content=body, headers=headers)
        assert first.status_code == 200
        assert first.json()["status"] == "processed"

        second = db_backed_client.post(URL, content=body, headers=headers)
        assert second.status_code == 200
        assert second.json()["status"] == "duplicate"

    def test_same_event_id_different_payload_is_409(self, db_backed_client: TestClient, db_session: Session):
        connection, raw_key, secret = _make_connection_with_credentials(db_session)
        event_id = f"evt-{uuid.uuid4().hex}"
        first_payload = _payload(event_id)
        body, headers = _signed_request(first_payload, api_key=raw_key, secret=secret, event_id=event_id)
        first = db_backed_client.post(URL, content=body, headers=headers)
        assert first.status_code == 200

        second_payload = _payload(event_id)
        second_payload["data"]["note"] = "A completely different note."
        body2, headers2 = _signed_request(second_payload, api_key=raw_key, secret=secret, event_id=event_id)
        second = db_backed_client.post(URL, content=body2, headers=headers2)
        assert second.status_code == 409


class TestNoArbitraryMutation:
    def test_processing_an_inbound_event_never_touches_business_tables(
        self, db_backed_client: TestClient, db_session: Session
    ):
        connection, raw_key, secret = _make_connection_with_credentials(db_session)
        before_enquiries = db_session.scalars(select(Enquiry.id)).all()
        before_appts = db_session.scalars(select(AppointmentRequest.id)).all()
        before_handoffs = db_session.scalars(select(HumanHandoff.id)).all()

        event_id = f"evt-{uuid.uuid4().hex}"
        body, headers = _signed_request(_payload(event_id), api_key=raw_key, secret=secret, event_id=event_id)
        response = db_backed_client.post(URL, content=body, headers=headers)
        assert response.status_code == 200

        assert db_session.scalars(select(Enquiry.id)).all() == before_enquiries
        assert db_session.scalars(select(AppointmentRequest.id)).all() == before_appts
        assert db_session.scalars(select(HumanHandoff.id)).all() == before_handoffs
