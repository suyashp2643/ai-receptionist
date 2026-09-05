"""Service layer for tenant-configured IntegrationConnections: creation,
config/event-subscription updates, secret rotation, status transitions,
live verification, and dead-letter replay. This is the ONE place a
connector's signing secret is ever encrypted or decrypted outside the
delivery worker itself (app/services/outbox_worker_service.py) — no route
handler touches app.core.crypto directly.

Every mutation records an ActivityEvent (app/services/activity_service.py)
— never with a secret value, only `redact_secret_for_display`'s
presence/absence marker — so a tenant's operational audit trail shows
*that* a secret was rotated and by whom, never *what* it was.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import Settings
from app.core.crypto import (
    api_key_display_metadata,
    decrypt_secret,
    encrypt_secret,
    generate_api_key,
    hash_api_key,
    redact_secret_for_display,
)
from app.integrations.connectors.base import ConnectorConfigError
from app.integrations.connectors.factory import get_connector
from app.integrations.connectors.sales_employee import ALLOWED_EVENT_TYPES as SALES_EMPLOYEE_ALLOWED_EVENT_TYPES
from app.integrations.envelope import EventType
from app.models.enums import IntegrationConnectionStatus, IntegrationConnectorType
from app.models.integration import IntegrationConnection, IntegrationOutboxEvent
from app.repositories.integration import IntegrationConnectionRepository, IntegrationOutboxEventRepository
from app.services import activity_service, outbox_producer_service, outbox_worker_service
from app.services.concurrency import apply_versioned_update


class IntegrationConfigError(ValueError):
    """Raised for an invalid connector config, name conflict, or
    event-type selection — the API layer maps this to a 422."""


def _valid_event_type_values() -> frozenset[str]:
    # connection.test_event is never explicitly subscribed — send_test_event
    # always produces it regardless of enabled_event_types (see that
    # function below and outbox_producer_service.produce_test_event).
    return frozenset(t.value for t in EventType) - {EventType.CONNECTION_TEST_EVENT.value}


def _validate_event_types(
    event_types: list[str], *, connector_type: IntegrationConnectorType, settings: Settings
) -> list[str]:
    if len(event_types) > settings.integration_max_enabled_event_types:
        raise IntegrationConfigError(
            f"At most {settings.integration_max_enabled_event_types} event types may be enabled."
        )
    valid = _valid_event_type_values()
    deduped = sorted(set(event_types))
    for event_type in deduped:
        if event_type not in valid:
            raise IntegrationConfigError(f"'{event_type}' is not a recognized event type.")
    if connector_type == IntegrationConnectorType.SALES_EMPLOYEE:
        allowed = {t.value for t in SALES_EMPLOYEE_ALLOWED_EVENT_TYPES}
        disallowed = [event_type for event_type in deduped if event_type not in allowed]
        if disallowed:
            raise IntegrationConfigError(f"A Sales Employee connection cannot subscribe to: {', '.join(disallowed)}.")
    return deduped


def list_connections(db: Session, tenant_id: uuid.UUID) -> Sequence[IntegrationConnection]:
    return IntegrationConnectionRepository(db, tenant_id).list_recent(limit=200, offset=0)


def get_connection(db: Session, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> IntegrationConnection | None:
    return IntegrationConnectionRepository(db, tenant_id).get(connection_id)


def create_connection(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    connector_type: IntegrationConnectorType,
    name: str,
    config: dict,
    enabled_event_types: list[str],
    signing_secret: str | None,
    settings: Settings,
) -> IntegrationConnection:
    repo = IntegrationConnectionRepository(db, tenant_id)
    if repo.get_by_name(name) is not None:
        raise IntegrationConfigError(f"A connection named '{name}' already exists.")

    connector = get_connector(connector_type)
    try:
        normalized_config = connector.validate_config(config, settings=settings)
    except ConnectorConfigError as exc:
        raise IntegrationConfigError(str(exc)) from exc

    validated_event_types = _validate_event_types(enabled_event_types, connector_type=connector_type, settings=settings)

    if connector.capabilities.requires_signing_secret and not signing_secret:
        raise IntegrationConfigError(f"{connector_type.value} connections require a signing secret.")

    ciphertext = None
    key_version = None
    if signing_secret:
        ciphertext, key_version = encrypt_secret(signing_secret, settings=settings)

    connection = IntegrationConnection(
        tenant_id=tenant_id,
        connector_type=connector_type,
        name=name,
        status=IntegrationConnectionStatus.CONFIGURED,
        config=normalized_config,
        enabled_event_types=validated_event_types,
        signing_secret_ciphertext=ciphertext,
        signing_secret_key_version=key_version,
        created_by_user_id=actor_user_id,
    )
    repo.add(connection)
    db.flush()

    activity_service.record(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action_type="integration.connection_created",
        entity_type="integration_connection",
        entity_id=connection.id,
        metadata={
            "connector_type": connector_type.value,
            "name": name,
            "signing_secret": redact_secret_for_display(signing_secret),
        },
    )
    return connection


def update_config_and_events(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    connection: IntegrationConnection,
    config: dict,
    enabled_event_types: list[str],
    expected_version: int,
    settings: Settings,
) -> IntegrationConnection:
    connector = get_connector(connection.connector_type)
    try:
        normalized_config = connector.validate_config(config, settings=settings)
    except ConnectorConfigError as exc:
        raise IntegrationConfigError(str(exc)) from exc
    validated_event_types = _validate_event_types(
        enabled_event_types, connector_type=connection.connector_type, settings=settings
    )

    apply_versioned_update(
        db,
        connection,
        expected_version=expected_version,
        values={"config": normalized_config, "enabled_event_types": validated_event_types},
    )
    activity_service.record(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action_type="integration.connection_updated",
        entity_type="integration_connection",
        entity_id=connection.id,
        metadata={"enabled_event_types": validated_event_types},
    )
    return connection


def rotate_signing_secret(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    connection: IntegrationConnection,
    new_secret: str,
    expected_version: int,
    settings: Settings,
) -> IntegrationConnection:
    ciphertext, key_version = encrypt_secret(new_secret, settings=settings)
    apply_versioned_update(
        db,
        connection,
        expected_version=expected_version,
        values={"signing_secret_ciphertext": ciphertext, "signing_secret_key_version": key_version},
    )
    activity_service.record(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action_type="integration.signing_secret_rotated",
        entity_type="integration_connection",
        entity_id=connection.id,
        metadata={},
    )
    return connection


def generate_inbound_api_key(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    connection: IntegrationConnection,
    expected_version: int,
    settings: Settings,
) -> str:
    """Returns the raw key exactly once — the caller (the API route) must
    return it in this response and never persist or log it. Only the hash
    and display metadata are stored."""
    raw_key = generate_api_key(prefix=settings.integration_api_key_prefix)
    key_hash = hash_api_key(raw_key)
    prefix, last_four = api_key_display_metadata(raw_key, prefix=settings.integration_api_key_prefix)
    is_rotation = connection.inbound_api_key_hash is not None
    now = datetime.now(UTC)
    values: dict = {
        "inbound_api_key_hash": key_hash,
        "inbound_api_key_prefix": prefix,
        "inbound_api_key_last_four": last_four,
        "inbound_api_key_rotated_at": now if is_rotation else None,
    }
    if not is_rotation:
        values["inbound_api_key_created_at"] = now
    apply_versioned_update(db, connection, expected_version=expected_version, values=values)
    activity_service.record(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action_type="integration.inbound_key_rotated" if is_rotation else "integration.inbound_key_created",
        entity_type="integration_connection",
        entity_id=connection.id,
        metadata={"prefix": prefix, "last_four": last_four},
    )
    return raw_key


def _set_status(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    connection: IntegrationConnection,
    new_status: IntegrationConnectionStatus,
    expected_version: int,
    action_type: str,
) -> IntegrationConnection:
    apply_versioned_update(db, connection, expected_version=expected_version, values={"status": new_status})
    activity_service.record(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action_type=action_type,
        entity_type="integration_connection",
        entity_id=connection.id,
        metadata={"to": new_status.value},
    )
    return connection


def pause_connection(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    connection: IntegrationConnection,
    expected_version: int,
) -> IntegrationConnection:
    return _set_status(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        connection=connection,
        new_status=IntegrationConnectionStatus.PAUSED,
        expected_version=expected_version,
        action_type="integration.connection_paused",
    )


def resume_connection(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    connection: IntegrationConnection,
    expected_version: int,
) -> IntegrationConnection:
    # Resumes to CONFIGURED, not straight back to VERIFIED — a paused
    # connection's health is unknown until it actually delivers again.
    return _set_status(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        connection=connection,
        new_status=IntegrationConnectionStatus.CONFIGURED,
        expected_version=expected_version,
        action_type="integration.connection_resumed",
    )


def disable_connection(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    connection: IntegrationConnection,
    expected_version: int,
) -> IntegrationConnection:
    return _set_status(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        connection=connection,
        new_status=IntegrationConnectionStatus.DISABLED,
        expected_version=expected_version,
        action_type="integration.connection_disabled",
    )


def verify_connection_now(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    connection: IntegrationConnection,
    settings: Settings,
):
    """Live "test connection" call — makes a real network request (for
    webhook-family connectors) via the connector's own verify_connection.
    Never called under a held DB lock: the config/secret are read here,
    but the network call happens after this function's own DB work, same
    separation the delivery worker enforces (see
    app/services/outbox_worker_service.py)."""
    connector = get_connector(connection.connector_type)
    secret = None
    if connection.signing_secret_ciphertext:
        secret = decrypt_secret(
            connection.signing_secret_ciphertext,
            key_version=connection.signing_secret_key_version or 0,
            settings=settings,
        )
    outcome = connector.verify_connection(config=connection.config, secret=secret, settings=settings)

    if outcome.success:
        connection.status = IntegrationConnectionStatus.VERIFIED
        connection.last_verified_at = datetime.now(UTC)
        connection.failure_count = 0
        connection.version += 1
    activity_service.record(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action_type="integration.connection_verified" if outcome.success else "integration.connection_verify_failed",
        entity_type="integration_connection",
        entity_id=connection.id,
        metadata={"success": outcome.success},
    )
    db.flush()
    return outcome


def send_test_event(
    db: Session, *, tenant_id: uuid.UUID, actor_user_id: uuid.UUID, connection: IntegrationConnection
) -> IntegrationOutboxEvent:
    row = outbox_producer_service.produce_test_event(db, connection=connection, triggered_by=f"user:{actor_user_id}")
    activity_service.record(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action_type="integration.test_event_sent",
        entity_type="integration_connection",
        entity_id=connection.id,
        metadata={"outbox_event_id": str(row.id)},
    )
    return row


def replay_dead_letter(db: Session, *, tenant_id: uuid.UUID, actor_user_id: uuid.UUID, event_id: uuid.UUID) -> bool:
    repo = IntegrationOutboxEventRepository(db)
    replayed = repo.replay_dead_letter(tenant_id=tenant_id, event_id=event_id)
    if replayed:
        activity_service.record(
            db,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action_type="integration.delivery_replayed",
            entity_type="integration_outbox_event",
            entity_id=event_id,
            metadata={},
        )
    return replayed


def process_pending_now(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    connection: IntegrationConnection,
    settings: Settings,
    batch_size: int = 25,
):
    """An authenticated, on-demand, tenant-and-connection-scoped delivery
    pass — used by the dashboard's integration lab (and available as a
    general "process now" convenience) so a demo doesn't require running
    the CLI worker separately. This is NOT a scheduler: it runs exactly
    once, synchronously, for exactly this request, and only ever touches
    this connection's own due rows (see
    IntegrationOutboxEventRepository.claim_batch's tenant_id/connection_id
    scoping) — never another tenant's or another connection's backlog.

    `outbox_worker_service.run_once` opens its OWN real
    `session_scope()` internally (the same contract the real background
    worker uses) — entirely separate from `db` here, which is only used
    to record the activity event afterward, exactly like every other
    function in this module."""
    result = outbox_worker_service.run_once(
        settings=settings, tenant_id=tenant_id, connection_id=connection.id, batch_size=batch_size
    )
    activity_service.record(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action_type="integration.processed_pending_now",
        entity_type="integration_connection",
        entity_id=connection.id,
        metadata={
            "claimed": result.claimed,
            "delivered": result.delivered,
            "retried": result.retried,
            "dead_lettered": result.dead_lettered,
        },
    )
    return result
