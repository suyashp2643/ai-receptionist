"""A deterministic, zero-network connector used by the automated test
suite and the integration lab (app/api/v1/integrations_lab.py). Never
makes a real network call — this is what makes the lab "zero-cost" and
safe to demo without any external receiver running.

`config["mode"]` selects the deterministic outcome:
  "success" (default) — verify and deliver always succeed.
  "failure"            — verify and deliver always report a retryable
                          failure (simulates a receiver that is down).
  "permanent_failure"  — deliver reports a permanent (non-retryable)
                          failure (simulates a receiver rejecting the
                          payload itself, e.g. a 400).
"""

from __future__ import annotations

import uuid
from typing import ClassVar

from app.config import Settings
from app.integrations.connectors.base import (
    Connector,
    ConnectorCapabilities,
    ConnectorConfigError,
    DeliveryOutcome,
    VerifyOutcome,
)
from app.integrations.envelope import EventEnvelope
from app.models.enums import DeliveryAttemptStatus, IntegrationConnectorType

_VALID_MODES = frozenset({"success", "failure", "permanent_failure"})


class MockConnector(Connector):
    connector_type: ClassVar[IntegrationConnectorType] = IntegrationConnectorType.MOCK
    capabilities: ClassVar[ConnectorCapabilities] = ConnectorCapabilities(
        requires_destination_url=False, requires_signing_secret=False, supports_verify=True
    )

    def validate_config(self, config: dict, *, settings: Settings) -> dict:
        mode = config.get("mode", "success")
        if mode not in _VALID_MODES:
            raise ConnectorConfigError(f"mode must be one of {sorted(_VALID_MODES)}.")
        return {"mode": mode}

    def verify_connection(self, *, config: dict, secret: str | None, settings: Settings) -> VerifyOutcome:
        if config.get("mode") == "success":
            return VerifyOutcome(success=True)
        return VerifyOutcome(success=False, error_summary="Mock connector configured to fail verification.")

    def deliver(
        self,
        *,
        config: dict,
        secret: str | None,
        envelope: EventEnvelope,
        delivery_id: uuid.UUID,
        settings: Settings,
    ) -> DeliveryOutcome:
        mode = config.get("mode", "success")
        if mode == "success":
            return DeliveryOutcome(
                status=DeliveryAttemptStatus.SUCCESS, http_status_code=200, error_summary=None, duration_ms=1
            )
        if mode == "permanent_failure":
            return DeliveryOutcome(
                status=DeliveryAttemptStatus.PERMANENT_FAILURE,
                http_status_code=400,
                error_summary="Mock connector configured to permanently fail.",
                duration_ms=1,
            )
        return DeliveryOutcome(
            status=DeliveryAttemptStatus.RETRYABLE_FAILURE,
            http_status_code=503,
            error_summary="Mock connector configured to fail.",
            duration_ms=1,
        )
