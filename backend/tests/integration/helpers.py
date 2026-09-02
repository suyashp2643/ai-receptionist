"""Shared setup/request helpers for the multi-connection integration tests.

Every helper here goes through the real HTTP API (`real_client`) rather
than touching the database directly with factory functions — the whole
point of this package is to exercise genuinely separate, per-request
sessions/connections exactly as production does, and a direct-to-DB
shortcut would undermine that for whichever step it replaced.
"""

import json
import uuid
from concurrent.futures import ThreadPoolExecutor

TEST_PASSWORD = "MultiConnTest123!"  # noqa: S105 - fixed test-only password, not a secret


def unique_email(label: str) -> str:
    return f"multiconn-{label}-{uuid.uuid4().hex[:12]}@example.com"


def register_tenant(client, cleanup_tenants, *, label: str) -> tuple[dict, str]:
    """Registers a brand-new, uniquely identifiable tenant via the real
    `/auth/register` endpoint and registers both its tenant id and its
    owning user id with `cleanup_tenants` (a `CreatedTestData`, see
    `conftest.py`) for teardown. Returns (auth_headers, tenant_id)."""
    suffix = uuid.uuid4().hex[:10]
    email = unique_email(label)
    response = client.post(
        "/api/v1/auth/register",
        json={
            "display_name": f"MultiConn {label}",
            "email": email,
            "password": TEST_PASSWORD,
            "workspace_name": f"MultiConn Test {label} {suffix}",
            "timezone": "UTC",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    tenant_id = body["memberships"][0]["tenant_id"]
    cleanup_tenants.tenant_ids.append(tenant_id)
    cleanup_tenants.user_ids.append(body["user"]["id"])
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    return headers, tenant_id


def setup_active_receptionist(
    client, headers: dict, tenant_id: str, *, with_tool_trigger: bool = False
) -> str:
    """Creates and activates a receptionist for `tenant_id`. When
    `with_tool_trigger` is set, also enables `answer_questions` and adds an
    FAQ so a grounded question reliably invokes the `get_business_hours`
    tool and persists a tool-role message alongside the assistant message
    in the same transaction — the exact shape that reproduced the
    sequence-number collision."""
    response = client.post(
        f"/api/v1/tenants/{tenant_id}/receptionists",
        json={"name": "MultiConn Receptionist"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    receptionist_id = response.json()["id"]

    response = client.patch(
        f"/api/v1/tenants/{tenant_id}/receptionists/{receptionist_id}",
        json={"status": "active"},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    if with_tool_trigger:
        response = client.patch(
            f"/api/v1/tenants/{tenant_id}/receptionists/{receptionist_id}/workflow",
            json={"enabled_actions": ["answer_questions"]},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        response = client.post(
            f"/api/v1/tenants/{tenant_id}/faqs",
            json={"question": "What are your hours?", "answer": "We are open 9-5 Monday to Friday."},
            headers=headers,
        )
        assert response.status_code == 201, response.text

    return receptionist_id


def start_conversation(client, headers: dict, tenant_id: str, receptionist_id: str) -> str:
    response = client.post(
        f"/api/v1/tenants/{tenant_id}/receptionists/{receptionist_id}/test-conversations",
        json={},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        event_name = None
        data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:") :].strip())
        if event_name is not None:
            events.append({"event": event_name, "data": data})
    return events


def send_message(
    executor: ThreadPoolExecutor,
    client,
    tenant_id: str,
    conversation_id: str,
    headers: dict,
    content: str,
    *,
    idempotency_key: str | None = None,
    timeout: float = 15.0,
):
    """Submits one message through a worker thread and bounds the wait with
    `timeout` — a genuine lock regression fails this call with a
    `TimeoutError` instead of hanging the test (and the whole suite)
    indefinitely. Returns (response, parsed_sse_events)."""
    body: dict = {"content": content}
    if idempotency_key is not None:
        body["idempotency_key"] = idempotency_key
    future = executor.submit(
        client.post,
        f"/api/v1/tenants/{tenant_id}/test-conversations/{conversation_id}/messages",
        json=body,
        headers=headers,
    )
    response = future.result(timeout=timeout)
    return response, parse_sse(response.text)


def get_conversation(client, tenant_id: str, conversation_id: str, headers: dict) -> dict:
    response = client.get(
        f"/api/v1/tenants/{tenant_id}/test-conversations/{conversation_id}",
        params={"message_limit": 200},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()
