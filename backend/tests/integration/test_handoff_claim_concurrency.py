"""PostgreSQL multi-connection integration test for Phase 6's atomic
handoff claim. Two distinct tenant members racing to claim the same open
handoff must never both succeed — HumanHandoffRepository.claim_atomically
uses a single conditional `UPDATE ... WHERE status = 'open'`, never a
read-then-write, specifically to make this true across genuinely separate
connections, not just within one already-serialized test session (which
`tests/test_dashboard_records_api.py`'s service-layer test already checks
for the single-connection case).
"""

import uuid

import pytest
from app.config import get_settings
from app.core.normalization import normalize_email
from app.core.security import create_access_token, hash_password
from sqlalchemy import text

from tests.integration.helpers import register_tenant, setup_active_receptionist

pytestmark = pytest.mark.multiconn

settings = get_settings()


def _add_second_member(engine, cleanup_tenants, *, tenant_id: str) -> dict:
    """Directly inserts a second real, committed user + membership — there
    is no public "invite a teammate" endpoint yet, so this is the only way
    to get a genuinely second tenant member for a real race test."""
    user_id = str(uuid.uuid4())
    email = f"multiconn-claimant-{uuid.uuid4().hex[:10]}@example.com"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users "
                "(id, normalized_email, password_hash, display_name, is_active, created_at, updated_at) "
                "VALUES (:id, :email, :password_hash, 'Second Claimant', true, now(), now())"
            ),
            {"id": user_id, "email": normalize_email(email), "password_hash": hash_password("irrelevant-password")},
        )
        conn.execute(
            text(
                "INSERT INTO tenant_members (id, tenant_id, user_id, role, status, created_at, updated_at) "
                "VALUES (:id, :tenant_id, :user_id, 'member', 'active', now(), now())"
            ),
            {"id": str(uuid.uuid4()), "tenant_id": tenant_id, "user_id": user_id},
        )
    cleanup_tenants.user_ids.append(user_id)
    token, _ = create_access_token(settings=settings, user_id=uuid.UUID(user_id), session_id=uuid.uuid4())
    return {"Authorization": f"Bearer {token}"}


def _insert_conversation_and_open_handoff(engine, *, tenant_id: str, receptionist_id: str) -> str:
    conversation_id = str(uuid.uuid4())
    handoff_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO conversations (id, tenant_id, receptionist_id, mode, channel, provider, status, "
                "locale, collected_data, missing_required_fields, qualification_complete, safety_state, "
                "had_safety_event, had_clinic_emergency, started_at, created_at, updated_at) "
                "VALUES (:id, :tenant_id, :receptionist_id, 'widget', 'widget', 'mock', 'active', "
                "'en', '{}', '[]', false, '{}', false, false, now(), now(), now())"
            ),
            {"id": conversation_id, "tenant_id": tenant_id, "receptionist_id": receptionist_id},
        )
        conn.execute(
            text(
                "INSERT INTO human_handoffs (id, tenant_id, receptionist_id, conversation_id, reason, status, "
                "version, created_at, updated_at) "
                "VALUES (:id, :tenant_id, :receptionist_id, :conversation_id, 'Please call me back', 'open', "
                "1, now(), now())"
            ),
            {
                "id": handoff_id,
                "tenant_id": tenant_id,
                "receptionist_id": receptionist_id,
                "conversation_id": conversation_id,
            },
        )
    return handoff_id


class TestAtomicHandoffClaim:
    def test_two_simultaneous_claims_only_one_succeeds(self, real_client, executor, cleanup_tenants, multiconn_engine):
        headers_a, tenant_id = register_tenant(real_client, cleanup_tenants, label="claimA")
        receptionist_id = setup_active_receptionist(real_client, headers_a, tenant_id)
        headers_b = _add_second_member(multiconn_engine, cleanup_tenants, tenant_id=tenant_id)
        handoff_id = _insert_conversation_and_open_handoff(
            multiconn_engine, tenant_id=tenant_id, receptionist_id=receptionist_id
        )

        future_a = executor.submit(
            real_client.post, f"/api/v1/tenants/{tenant_id}/handoffs/{handoff_id}/claim", headers=headers_a
        )
        future_b = executor.submit(
            real_client.post, f"/api/v1/tenants/{tenant_id}/handoffs/{handoff_id}/claim", headers=headers_b
        )
        response_a = future_a.result(timeout=10)
        response_b = future_b.result(timeout=10)

        statuses = sorted([response_a.status_code, response_b.status_code])
        assert statuses == [200, 409], (
            response_a.status_code,
            response_a.text,
            response_b.status_code,
            response_b.text,
        )

        detail = real_client.get(f"/api/v1/tenants/{tenant_id}/handoffs/{handoff_id}", headers=headers_a)
        assert detail.status_code == 200
        assert detail.json()["status"] == "claimed"
        assert detail.json()["version"] == 2
