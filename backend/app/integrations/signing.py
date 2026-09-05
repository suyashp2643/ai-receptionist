"""HMAC-SHA256 request signing shared by every connector that delivers over
HTTP (webhook, Revenue Brain, Sales Employee — see
app/integrations/connectors/). One signing scheme for all of them, so a
receiver only ever has to implement verification once.

Signed material is `f"{timestamp}.{delivery_id}.{event_id}.{schema_version}.{body}"`
— including the delivery id (not just the event id) means a retried
delivery of the same event produces a different signature each attempt,
so a receiver cannot mistake signature reuse for a legitimate replay
signal; idempotency is instead the receiver's own job, keyed off
`event_id` in the body, which is stable across retries.
"""

from __future__ import annotations

import hashlib
import hmac
import time

HEADER_SIGNATURE = "X-Integration-Signature"
HEADER_TIMESTAMP = "X-Integration-Timestamp"
HEADER_DELIVERY_ID = "X-Integration-Delivery-Id"
HEADER_EVENT_ID = "X-Integration-Event-Id"
HEADER_SCHEMA_VERSION = "X-Integration-Schema-Version"

# A receiver should reject a signature whose timestamp is further from "now"
# than this — bounds how long a captured request could be replayed even if
# an attacker somehow obtained a valid signed body. Documented for receiver
# implementers in docs/integration-contracts.md; not itself enforced by the
# sender (the sender only ever sends a fresh timestamp).
REPLAY_WINDOW_SECONDS = 300


def current_timestamp() -> str:
    return str(int(time.time()))


def _signing_string(*, timestamp: str, delivery_id: str, event_id: str, schema_version: str, body: bytes) -> bytes:
    return f"{timestamp}.{delivery_id}.{event_id}.{schema_version}.".encode() + body


def sign_payload(
    secret: str,
    *,
    body: bytes,
    timestamp: str,
    delivery_id: str,
    event_id: str,
    schema_version: str,
) -> str:
    message = _signing_string(
        timestamp=timestamp, delivery_id=delivery_id, event_id=event_id, schema_version=schema_version, body=body
    )
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_signature(
    secret: str,
    *,
    signature: str,
    body: bytes,
    timestamp: str,
    delivery_id: str,
    event_id: str,
    schema_version: str,
) -> bool:
    """Constant-time comparison — used by the inbound API (a future
    receiver of OUR inbound events might reuse this too, but today it
    verifies nothing inbound; kept here so sign/verify never drift apart)."""
    expected = sign_payload(
        secret,
        body=body,
        timestamp=timestamp,
        delivery_id=delivery_id,
        event_id=event_id,
        schema_version=schema_version,
    )
    return hmac.compare_digest(expected, signature)
