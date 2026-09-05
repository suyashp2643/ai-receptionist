"""Writes IntegrationOutboxEvent rows for every tenant connection
subscribed to a domain event — the transactional-outbox write half. This
module never commits: it only calls `db.add`/`db.execute` against the
Session it is given, so the caller's own transaction (the same one that
just wrote the domain mutation — the enquiry, appointment request,
handoff, etc.) either commits both together or rolls back both together.
That atomicity is the entire point of the outbox pattern — see
app/models/integration.py's module docstring and
docs/integration-contracts.md.

Idempotent by construction: `INSERT ... ON CONFLICT DO NOTHING` against
the (tenant_id, connection_id, dedup_key) unique constraint means calling
`produce_event` twice for the same domain occurrence (e.g. a retried
request handler) creates at most one outbox row per connection, with no
race window and no need for the caller to pre-check existence.
"""

from __future__ import annotations

import uuid

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.integrations.connectors.sales_employee import ALLOWED_EVENT_TYPES as SALES_EMPLOYEE_ALLOWED_EVENT_TYPES
from app.integrations.envelope import BaseEventPayload, ConnectionTestEventPayload, EventType, build_envelope
from app.models.enums import INTEGRATION_DELIVERABLE_STATUSES, IntegrationConnectorType
from app.models.integration import IntegrationConnection, IntegrationOutboxEvent
from app.repositories.integration import IntegrationConnectionRepository


def produce_event(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    event_type: EventType,
    payload: BaseEventPayload,
    dedup_key: str,
    correlation_id: uuid.UUID | None = None,
    causation_id: uuid.UUID | None = None,
) -> int:
    """Returns the number of connections an outbox row was produced for
    (0 if the tenant has no subscribed, deliverable connections — the
    common case for most tenants, who have configured no integrations)."""
    connection_repo = IntegrationConnectionRepository(db, tenant_id)
    subscribed = connection_repo.list_subscribed(event_type.value)
    if not subscribed:
        return 0

    envelope = build_envelope(
        event_type, tenant_id=tenant_id, payload=payload, correlation_id=correlation_id, causation_id=causation_id
    )
    envelope_json = envelope.model_dump(mode="json", by_alias=True)

    produced = 0
    for connection in subscribed:
        if connection.status not in INTEGRATION_DELIVERABLE_STATUSES:
            continue
        if connection.connector_type == IntegrationConnectorType.SALES_EMPLOYEE:
            if event_type not in SALES_EMPLOYEE_ALLOWED_EVENT_TYPES:
                # Defense in depth — app/services/integration_connection_service.py
                # already rejects enabling a disallowed event type on a Sales
                # Employee connection at config time, so this should be
                # unreachable; skipping rather than raising keeps a single
                # misconfigured connection from blocking every OTHER
                # connection's event production.
                continue

        stmt = (
            pg_insert(IntegrationOutboxEvent)
            .values(
                tenant_id=tenant_id,
                connection_id=connection.id,
                event_id=envelope.event_id,
                event_type=event_type.value,
                event_version=envelope.event_version,
                dedup_key=dedup_key,
                payload=envelope_json,
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "connection_id", "dedup_key"],
            )
            .returning(IntegrationOutboxEvent.id)
        )
        # `.rowcount` is unreliable for INSERT ... ON CONFLICT DO NOTHING
        # across DBAPI drivers (psycopg reports -1, which is truthy in
        # Python — silently over-counting every skipped duplicate).
        # `.returning(...)` only yields a row when a row was actually
        # inserted, so checking the fetched result is the only accurate
        # way to know whether this call produced a new row or hit the
        # dedup conflict.
        result = db.execute(stmt)
        if result.first() is not None:
            produced += 1
    return produced


def produce_test_event(db: Session, *, connection: IntegrationConnection, triggered_by: str) -> IntegrationOutboxEvent:
    """Always produces a row regardless of the connection's
    enabled_event_types or status — a test send is an explicit,
    authenticated owner/admin action (dashboard "Send test event" or the
    integration lab), not a subscription-driven production. Deliberately
    NOT deduplicated: each call is a new, deliberate test."""
    envelope = build_envelope(
        EventType.CONNECTION_TEST_EVENT,
        tenant_id=connection.tenant_id,
        payload=ConnectionTestEventPayload(triggered_by=triggered_by),
    )
    row = IntegrationOutboxEvent(
        tenant_id=connection.tenant_id,
        connection_id=connection.id,
        event_id=envelope.event_id,
        event_type=envelope.event_type.value,
        event_version=envelope.event_version,
        dedup_key=f"test:{envelope.event_id}",
        payload=envelope.model_dump(mode="json", by_alias=True),
    )
    db.add(row)
    db.flush()
    return row
