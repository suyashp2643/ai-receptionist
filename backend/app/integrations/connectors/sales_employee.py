"""AI Sales Employee adapter — forward-compatible groundwork for a product
that does not exist yet in this codebase.

Hard constraint, worth stating explicitly rather than leaving implicit:
this connector (like every connector in Phase 8) is OUTBOUND-NOTIFICATION
ONLY. It delivers a read-only event envelope describing something that
already happened (a lead was captured, an enquiry was qualified, an
appointment was requested) to whatever system is configured to receive it.
Nothing in this class — or anywhere else in this phase — sends an email,
places a call, sends an SMS, or executes any other message/contact action
on a lead. If a future AI Sales Employee product wants to act on an event
this connector delivers, that action happens entirely on ITS side, in its
own codebase, under its own authorization; this connector has no callback,
no execution hook, and no capability to trigger one.

Event-type scope: only allow-listed lead/qualification-oriented event
types may be enabled on a Sales Employee connection — never
`safety.escalation_detected`, which is for human review, not a sales
workflow. Enforced by `allowed_event_types` below, checked by
app/services/outbox_producer_service.py before it will produce an event
for a connection of this type.
"""

from __future__ import annotations

from typing import ClassVar

from app.config import Settings
from app.integrations.connectors.base import ConnectorCapabilities, ConnectorConfigError
from app.integrations.connectors.webhook import WebhookConnector
from app.integrations.envelope import EventType
from app.models.enums import IntegrationConnectorType

ALLOWED_EVENT_TYPES: frozenset[EventType] = frozenset(
    {
        EventType.CONTACT_CAPTURED,
        EventType.ENQUIRY_CREATED,
        EventType.ENQUIRY_QUALIFIED,
        EventType.ENQUIRY_STATUS_CHANGED,
        EventType.APPOINTMENT_REQUEST_CREATED,
        EventType.APPOINTMENT_REQUEST_STATUS_CHANGED,
        EventType.CONNECTION_TEST_EVENT,
    }
)


class SalesEmployeeConnector(WebhookConnector):
    connector_type: ClassVar[IntegrationConnectorType] = IntegrationConnectorType.SALES_EMPLOYEE
    capabilities: ClassVar[ConnectorCapabilities] = ConnectorCapabilities(
        requires_destination_url=True, requires_signing_secret=True, supports_verify=True
    )

    def validate_config(self, config: dict, *, settings: Settings) -> dict:
        normalized = super().validate_config(config, settings=settings)
        if not normalized.get("destination_url"):
            raise ConnectorConfigError("destination_url is required for a Sales Employee connection.")
        return normalized
