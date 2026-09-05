"""Credential lifecycle and secret-at-rest tests that
tests/test_phase8_crypto.py, tests/test_phase8_integrations_api.py, and
tests/test_phase8_integrations_inbound_api.py don't already fully cover:
key rotation actually revoking the old key, Fernet's authenticated-
encryption property (not just "garbage input fails"), no plaintext secret
anywhere a raw SQL query could read it, and no duplicate side effect from
a replayed inbound request."""

import json
import time
import uuid

import pytest
from app.config import Settings, get_settings
from app.core.crypto import SecretDecryptionError, decrypt_secret, encrypt_secret
from app.core.security import create_access_token
from app.integrations.signing import HEADER_SIGNATURE, HEADER_TIMESTAMP, sign_payload
from app.models.activity_event import ActivityEvent
from app.models.enums import IntegrationConnectorType
from app.models.integration import InboundIntegrationEvent, IntegrationConnection
from app.services import integration_connection_service
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.factories import make_tenant, make_tenant_with_owner, make_user

settings = get_settings()


def _auth_headers(user) -> dict[str, str]:
    token, _ = create_access_token(settings=settings, user_id=user.id, session_id=uuid.uuid4())
    return {"Authorization": f"Bearer {token}"}


class TestApiKeyRotationRevokesThePreviousKey:
    def test_the_old_key_stops_authenticating_after_rotation(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        headers = _auth_headers(owner)
        created = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/integrations",
            headers=headers,
            json={
                "connector_type": "sales_employee",
                "name": "Rotation Test",
                "config": {"destination_url": "http://127.0.0.1:9999/hook"},
                "enabled_event_types": [],
                "signing_secret": "shared-secret",
            },
        )
        connection_id = created.json()["id"]
        version = created.json()["version"]

        first_key_response = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/integrations/{connection_id}/inbound-key",
            headers=headers,
            json={"expected_version": version},
        )
        old_raw_key = first_key_response.json()["api_key"]
        version = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/integrations/{connection_id}", headers=headers
        ).json()["version"]

        second_key_response = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/integrations/{connection_id}/inbound-key",
            headers=headers,
            json={"expected_version": version},
        )
        new_raw_key = second_key_response.json()["api_key"]
        assert old_raw_key != new_raw_key

        event_id = f"evt-{uuid.uuid4().hex}"
        body = json.dumps(
            {
                "external_event_id": event_id,
                "event_type": "lead.note",
                "event_version": 1,
                "data": {"external_reference": "ref-1", "note": "test"},
            }
        ).encode("utf-8")
        ts = str(int(time.time()))

        def _signed_headers(api_key: str) -> dict[str, str]:
            # The signing scheme uses the request's own external_event_id
            # as both delivery_id and event_id for the inbound direction
            # (see app/services/integration_inbound_service.py) — must
            # match the body's actual external_event_id exactly, or
            # verification fails as a (correctly) invalid signature.
            signature = sign_payload(
                "shared-secret", body=body, timestamp=ts, delivery_id=event_id, event_id=event_id, schema_version="1"
            )
            return {
                "X-Integration-Api-Key": api_key,
                HEADER_SIGNATURE: signature,
                HEADER_TIMESTAMP: ts,
                "Content-Type": "application/json",
            }

        old_key_response = db_backed_client.post(
            "/api/v1/integrations/inbound/events", content=body, headers=_signed_headers(old_raw_key)
        )
        assert old_key_response.status_code == 401

        new_key_response = db_backed_client.post(
            "/api/v1/integrations/inbound/events", content=body, headers=_signed_headers(new_raw_key)
        )
        assert new_key_response.status_code == 200


class TestFernetAuthenticatedEncryption:
    def test_a_tampered_ciphertext_fails_to_decrypt(self):
        """Proves Fernet's *authentication*, not merely its secrecy — a
        single flipped byte in an otherwise-valid, correctly-encrypted
        token must be detected and rejected, never silently decrypted
        into corrupted plaintext."""
        fernet_key = Fernet.generate_key().decode("utf-8")
        test_settings = Settings(integration_encryption_key=fernet_key)
        ciphertext, key_version = encrypt_secret("a real signing secret", settings=test_settings)

        raw = bytearray(ciphertext.encode("utf-8"))
        # Flip one bit inside the token body (well past the fixed-format
        # version/timestamp prefix, so this reliably lands in the
        # authenticated ciphertext+HMAC region rather than a header byte
        # some Fernet versions tolerate differently).
        flip_index = len(raw) - 5
        raw[flip_index] ^= 0x01
        tampered_ciphertext = bytes(raw).decode("utf-8")

        with pytest.raises(SecretDecryptionError):
            decrypt_secret(tampered_ciphertext, key_version=key_version, settings=test_settings)


class TestNoPlaintextSecretInDatabaseReadableFields:
    def test_signing_secret_ciphertext_never_contains_the_plaintext(self, db_session: Session):
        tenant = make_tenant(db_session)
        actor = make_user(db_session)
        raw_secret = "extremely-sensitive-signing-secret-value-12345"
        connection = integration_connection_service.create_connection(
            db_session,
            tenant_id=tenant.id,
            actor_user_id=actor.id,
            connector_type=IntegrationConnectorType.WEBHOOK,
            name="Plaintext Check",
            config={"destination_url": "http://127.0.0.1:9999/hook"},
            enabled_event_types=[],
            signing_secret=raw_secret,
            settings=settings,
        )
        db_session.flush()

        row = db_session.scalars(select(IntegrationConnection).where(IntegrationConnection.id == connection.id)).first()
        assert raw_secret not in (row.signing_secret_ciphertext or "")
        assert raw_secret not in json.dumps(row.config)

        for activity in db_session.scalars(select(ActivityEvent).where(ActivityEvent.entity_id == connection.id)).all():
            assert raw_secret not in json.dumps(activity.event_metadata)

    def test_inbound_api_key_row_never_contains_the_raw_key(self, db_session: Session):
        tenant = make_tenant(db_session)
        actor = make_user(db_session)
        connection = integration_connection_service.create_connection(
            db_session,
            tenant_id=tenant.id,
            actor_user_id=actor.id,
            connector_type=IntegrationConnectorType.MOCK,
            name="Key Check",
            config={},
            enabled_event_types=[],
            signing_secret=None,
            settings=settings,
        )
        db_session.flush()
        raw_key = integration_connection_service.generate_inbound_api_key(
            db_session,
            tenant_id=tenant.id,
            actor_user_id=actor.id,
            connection=connection,
            expected_version=connection.version,
            settings=settings,
        )
        db_session.flush()

        row = db_session.scalars(select(IntegrationConnection).where(IntegrationConnection.id == connection.id)).first()
        assert row.inbound_api_key_hash != raw_key
        assert raw_key not in row.inbound_api_key_hash

        for activity in db_session.scalars(select(ActivityEvent).where(ActivityEvent.entity_id == connection.id)).all():
            assert raw_key not in json.dumps(activity.event_metadata)


class TestDuplicateInboundRequestProducesNoDuplicateSideEffect:
    def test_replaying_the_identical_signed_request_creates_exactly_one_record(
        self, db_backed_client: TestClient, db_session: Session
    ):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        headers = _auth_headers(owner)
        created = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/integrations",
            headers=headers,
            json={
                "connector_type": "sales_employee",
                "name": "Idempotency Check",
                "config": {"destination_url": "http://127.0.0.1:9999/hook"},
                "enabled_event_types": [],
                "signing_secret": "shared-secret",
            },
        )
        connection_id = created.json()["id"]
        version = created.json()["version"]
        key_response = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/integrations/{connection_id}/inbound-key",
            headers=headers,
            json={"expected_version": version},
        )
        raw_key = key_response.json()["api_key"]

        event_id = f"evt-{uuid.uuid4().hex}"
        body = json.dumps(
            {
                "external_event_id": event_id,
                "event_type": "lead.note",
                "event_version": 1,
                "data": {"external_reference": "ref-1", "note": "test"},
            }
        ).encode("utf-8")
        ts = str(int(time.time()))
        signature = sign_payload(
            "shared-secret", body=body, timestamp=ts, delivery_id=event_id, event_id=event_id, schema_version="1"
        )
        request_headers = {
            "X-Integration-Api-Key": raw_key,
            HEADER_SIGNATURE: signature,
            HEADER_TIMESTAMP: ts,
            "Content-Type": "application/json",
        }

        for _ in range(3):
            response = db_backed_client.post(
                "/api/v1/integrations/inbound/events", content=body, headers=request_headers
            )
            assert response.status_code == 200

        rows = db_session.scalars(
            select(InboundIntegrationEvent).where(InboundIntegrationEvent.connection_id == uuid.UUID(connection_id))
        ).all()
        assert len(rows) == 1

        activity_rows = db_session.scalars(
            select(ActivityEvent).where(
                ActivityEvent.entity_id == uuid.UUID(connection_id),
                ActivityEvent.action_type == "integration.inbound_event_received",
            )
        ).all()
        assert len(activity_rows) == 1
