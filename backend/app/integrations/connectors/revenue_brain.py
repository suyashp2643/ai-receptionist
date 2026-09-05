"""Revenue Brain adapter.

Revenue Brain is a separate product/repository — this codebase does not
import from it, link against it, or assume its internal implementation.
The contract between the two systems is exactly the versioned event
envelope defined in app/integrations/envelope.py, delivered exactly the
way WebhookConnector delivers any signed webhook (HMAC-SHA256, JSON body,
see app/integrations/signing.py). This class exists as its own connector
type — rather than tenants just picking WEBHOOK and pointing it at
Revenue Brain — so the dashboard can show a distinct, purpose-labeled
connector ("Revenue Brain") with its own defaults and so a future,
genuinely different Revenue Brain-specific transformation has a single
place to live without touching the generic webhook path.

Documented receiver contract (see docs/integration-contracts.md for the
full version): Revenue Brain's receiving endpoint is expected to accept a
`POST` with the standard envelope JSON body and the standard
`X-Integration-*` signing headers, verify the signature using the shared
secret configured on this connection, and respond `2xx` on success. No
other wire behavior is assumed.
"""

from __future__ import annotations

from typing import ClassVar

from app.config import Settings
from app.integrations.connectors.base import ConnectorCapabilities, ConnectorConfigError
from app.integrations.connectors.webhook import WebhookConnector
from app.models.enums import IntegrationConnectorType


class RevenueBrainConnector(WebhookConnector):
    connector_type: ClassVar[IntegrationConnectorType] = IntegrationConnectorType.REVENUE_BRAIN
    capabilities: ClassVar[ConnectorCapabilities] = ConnectorCapabilities(
        requires_destination_url=True, requires_signing_secret=True, supports_verify=True
    )

    def validate_config(self, config: dict, *, settings: Settings) -> dict:
        normalized = super().validate_config(config, settings=settings)
        # Revenue Brain integrations are never unsigned in this codebase —
        # enforced at the connection-service layer (which requires a
        # signing secret whenever capabilities.requires_signing_secret is
        # True), not here; this validate_config only handles destination/
        # header shape, same as the generic webhook connector.
        if not normalized.get("destination_url"):
            raise ConnectorConfigError("destination_url is required for a Revenue Brain connection.")
        return normalized
