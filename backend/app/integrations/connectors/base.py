"""The typed connector abstraction every integration adapter implements.

A connector is deliberately stateless and knows nothing about SQLAlchemy or
the outbox tables — it operates on plain `config`/`secret` values and
returns plain result dataclasses. This keeps two things true that matter a
lot for correctness:

  1. It is trivially testable without a database.
  2. The delivery worker (app/services/outbox_worker_service.py) can load a
     connection's config/secret INSIDE a short DB transaction, close that
     transaction, and only then call `deliver()` — the actual network call
     never happens while a database row/lock is held. See the orchestrator's
     own 3-phase-commit precedent (app/ai/orchestrator.py) for why that
     separation matters in this codebase.

`validate_config` and `verify_connection` DO make network/DNS calls (SSRF
validation, a live "test connection" ping) but are only ever invoked from
request-handling code paths that are not holding a long-lived transaction
around them either — see app/services/integration_connection_service.py.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from app.config import Settings
from app.integrations.envelope import EventEnvelope
from app.models.enums import DeliveryAttemptStatus, IntegrationConnectorType


class ConnectorConfigError(ValueError):
    """Raised for a `config` value that is malformed or unsafe. The message
    is safe to show to the authenticated owner/admin configuring the
    connection — never propagated to an unauthenticated caller."""


@dataclass(frozen=True)
class ConnectorCapabilities:
    requires_destination_url: bool
    requires_signing_secret: bool
    supports_verify: bool


@dataclass(frozen=True)
class VerifyOutcome:
    success: bool
    error_summary: str | None = None


@dataclass(frozen=True)
class DeliveryOutcome:
    status: DeliveryAttemptStatus
    http_status_code: int | None
    error_summary: str | None
    duration_ms: int


class Connector(ABC):
    connector_type: ClassVar[IntegrationConnectorType]
    capabilities: ClassVar[ConnectorCapabilities]

    @abstractmethod
    def validate_config(self, config: dict, *, settings: Settings) -> dict:
        """Returns a normalized copy of `config`. Raises ConnectorConfigError
        for anything invalid or unsafe (e.g. an SSRF-rejected destination).
        Called both when a connection is created/edited AND is safe to call
        again at any later point (e.g. before a delivery) since it performs
        no persistence itself."""

    @abstractmethod
    def verify_connection(self, *, config: dict, secret: str | None, settings: Settings) -> VerifyOutcome:
        """A synchronous "test now" call — used by the dashboard's Test
        Connection action and to promote CONFIGURED -> VERIFIED. Must never
        raise for an ordinary failure (a bad URL, a non-2xx response) —
        those are reported via VerifyOutcome.success=False; only a
        genuine programming error should raise."""

    @abstractmethod
    def deliver(
        self,
        *,
        config: dict,
        secret: str | None,
        envelope: EventEnvelope,
        delivery_id: uuid.UUID,
        settings: Settings,
    ) -> DeliveryOutcome:
        """Makes the actual delivery attempt. Must never raise for an
        ordinary delivery failure (timeout, non-2xx, connection refused) —
        those are reported via DeliveryOutcome; only a genuine programming
        error should raise. Must never block longer than
        settings.integration_delivery_connect_timeout_seconds +
        integration_delivery_read_timeout_seconds."""
