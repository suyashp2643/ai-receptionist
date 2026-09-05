"""Generic signed-webhook connector — an HMAC-SHA256-signed JSON POST to a
tenant-configured URL. This is the base delivery mechanism the Revenue
Brain and Sales Employee connectors both reuse (see revenue_brain.py /
sales_employee.py); WEBHOOK itself is the connector type for "any other
receiver", e.g. a tenant's own Zapier/Make catch-hook or internal service.

Every destination is validated through app/core/ssrf_guard.py, both at
config-save time (validate_config) and again immediately before every
delivery attempt (deliver) — DNS can change between the two, and this
connector never trusts a validation result older than the call it guards.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, ClassVar

import httpx

from app.config import Settings
from app.core.ssrf_guard import DestinationValidationError, validate_destination_url
from app.integrations.connectors.base import (
    Connector,
    ConnectorCapabilities,
    ConnectorConfigError,
    DeliveryOutcome,
    VerifyOutcome,
)
from app.integrations.envelope import ENVELOPE_SCHEMA, EventEnvelope
from app.integrations.field_mapping import FieldMappingError, apply_field_mapping, validate_field_mapping
from app.integrations.pinned_transport import build_pinned_transport
from app.integrations.signing import (
    HEADER_DELIVERY_ID,
    HEADER_EVENT_ID,
    HEADER_SCHEMA_VERSION,
    HEADER_SIGNATURE,
    HEADER_TIMESTAMP,
    current_timestamp,
    sign_payload,
)
from app.models.enums import DeliveryAttemptStatus, IntegrationConnectorType

# Custom headers a tenant may ask to attach to every request — an
# allow-list, not a free-form dict, so a connection config can never
# override the signing headers above, inject a Host header, or smuggle
# something like Authorization in a way that bypasses the connector's own
# secret handling. A tenant that needs bearer-token auth on top of HMAC
# signing can use this to set their own header name.
_ALLOWED_CUSTOM_HEADER_NAMES = frozenset({"x-api-key", "x-webhook-token", "x-source"})
_MAX_CUSTOM_HEADERS = 5
_MAX_CUSTOM_HEADER_VALUE_LENGTH = 500


def _validate_custom_headers(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConnectorConfigError("custom_headers must be an object of header name to value.")
    if len(raw) > _MAX_CUSTOM_HEADERS:
        raise ConnectorConfigError(f"custom_headers may have at most {_MAX_CUSTOM_HEADERS} entries.")
    normalized: dict[str, str] = {}
    for name, value in raw.items():
        if not isinstance(name, str) or name.lower() not in _ALLOWED_CUSTOM_HEADER_NAMES:
            raise ConnectorConfigError(f"custom_headers keys must be one of {sorted(_ALLOWED_CUSTOM_HEADER_NAMES)}.")
        if not isinstance(value, str) or not value or len(value) > _MAX_CUSTOM_HEADER_VALUE_LENGTH:
            raise ConnectorConfigError(f"custom_headers.{name} must be a non-empty string.")
        normalized[name.lower()] = value
    return normalized


class WebhookConnector(Connector):
    """Generic signed webhook. Subclassed (not instantiated directly for
    other connector types) by RevenueBrainConnector and
    SalesEmployeeConnector, which reuse this delivery mechanism and only
    override `connector_type` and, where their contract differs,
    `validate_config`/`capabilities`."""

    connector_type: ClassVar[IntegrationConnectorType] = IntegrationConnectorType.WEBHOOK
    capabilities: ClassVar[ConnectorCapabilities] = ConnectorCapabilities(
        requires_destination_url=True, requires_signing_secret=True, supports_verify=True
    )

    def validate_config(self, config: dict, *, settings: Settings) -> dict:
        destination_url = config.get("destination_url")
        if not isinstance(destination_url, str) or not destination_url:
            raise ConnectorConfigError("destination_url is required.")
        try:
            validated = validate_destination_url(destination_url, settings=settings)
        except DestinationValidationError as exc:
            raise ConnectorConfigError(str(exc)) from exc
        custom_headers = _validate_custom_headers(config.get("custom_headers"))
        field_mapping = config.get("field_mapping")
        if field_mapping is not None:
            try:
                validate_field_mapping(field_mapping, settings=settings)
            except FieldMappingError as exc:
                raise ConnectorConfigError(str(exc)) from exc
        return {"destination_url": validated.url, "custom_headers": custom_headers, "field_mapping": field_mapping}

    def _headers_and_body(
        self,
        *,
        envelope: EventEnvelope,
        delivery_id: uuid.UUID,
        secret: str | None,
        custom_headers: dict[str, str],
        field_mapping: dict | None,
        settings: Settings,
    ) -> tuple[dict[str, str], bytes]:
        if field_mapping:
            mapped_envelope = envelope.model_copy(
                update={
                    "data": apply_field_mapping(envelope.data, validate_field_mapping(field_mapping, settings=settings))
                }
            )
            body = mapped_envelope.model_dump_json(by_alias=True).encode("utf-8")
        else:
            body = envelope.model_dump_json(by_alias=True).encode("utf-8")
        headers = {"Content-Type": "application/json", **custom_headers}
        if secret:
            timestamp = current_timestamp()
            signature = sign_payload(
                secret,
                body=body,
                timestamp=timestamp,
                delivery_id=str(delivery_id),
                event_id=str(envelope.event_id),
                schema_version=str(envelope.event_version),
            )
            headers.update(
                {
                    HEADER_SIGNATURE: signature,
                    HEADER_TIMESTAMP: timestamp,
                    HEADER_DELIVERY_ID: str(delivery_id),
                    HEADER_EVENT_ID: str(envelope.event_id),
                    HEADER_SCHEMA_VERSION: ENVELOPE_SCHEMA,
                }
            )
        return headers, body

    def verify_connection(self, *, config: dict, secret: str | None, settings: Settings) -> VerifyOutcome:
        from app.integrations.envelope import ConnectionTestEventPayload, EventType, build_envelope

        destination_url = config.get("destination_url", "")
        try:
            validate_destination_url(destination_url, settings=settings)
        except DestinationValidationError as exc:
            return VerifyOutcome(success=False, error_summary=str(exc))

        envelope = build_envelope(
            EventType.CONNECTION_TEST_EVENT,
            tenant_id=uuid.uuid4(),
            payload=ConnectionTestEventPayload(triggered_by="verify_connection"),
        )
        outcome = self.deliver(
            config=config, secret=secret, envelope=envelope, delivery_id=uuid.uuid4(), settings=settings
        )
        if outcome.status == DeliveryAttemptStatus.SUCCESS:
            return VerifyOutcome(success=True)
        return VerifyOutcome(success=False, error_summary=outcome.error_summary)

    def deliver(
        self,
        *,
        config: dict,
        secret: str | None,
        envelope: EventEnvelope,
        delivery_id: uuid.UUID,
        settings: Settings,
    ) -> DeliveryOutcome:
        destination_url = config.get("destination_url", "")
        try:
            validated = validate_destination_url(destination_url, settings=settings)
        except DestinationValidationError as exc:
            return DeliveryOutcome(
                status=DeliveryAttemptStatus.PERMANENT_FAILURE,
                http_status_code=None,
                error_summary=str(exc),
                duration_ms=0,
            )

        headers, body = self._headers_and_body(
            envelope=envelope,
            delivery_id=delivery_id,
            secret=secret,
            custom_headers=config.get("custom_headers", {}),
            field_mapping=config.get("field_mapping"),
            settings=settings,
        )

        # Pinned to the exact IP validate_destination_url just resolved and
        # validated, not merely the hostname — closes the TOCTOU/DNS-
        # rebinding window between validation and connection. See
        # app/integrations/pinned_transport.py's own docstring for the
        # httpcore-level proof that this never weakens TLS/SNI/certificate
        # hostname verification. A fresh pin is built per attempt (never
        # cached), so a retry re-validates and re-pins from scratch.
        pinned_transport = build_pinned_transport(validated.resolved_ips[0], verify=validated.scheme == "https")

        started = time.monotonic()
        try:
            with httpx.Client(transport=pinned_transport, follow_redirects=False) as client:
                response = client.post(
                    validated.url,
                    content=body,
                    headers=headers,
                    timeout=httpx.Timeout(
                        connect=settings.integration_delivery_connect_timeout_seconds,
                        read=settings.integration_delivery_read_timeout_seconds,
                        write=settings.integration_delivery_read_timeout_seconds,
                        pool=settings.integration_delivery_connect_timeout_seconds,
                    ),
                )
        except httpx.TimeoutException as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            return DeliveryOutcome(
                status=DeliveryAttemptStatus.RETRYABLE_FAILURE,
                http_status_code=None,
                error_summary=f"Timed out: {type(exc).__name__}",
                duration_ms=duration_ms,
            )
        except httpx.HTTPError as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            return DeliveryOutcome(
                status=DeliveryAttemptStatus.RETRYABLE_FAILURE,
                http_status_code=None,
                error_summary=f"Connection error: {type(exc).__name__}",
                duration_ms=duration_ms,
            )
        duration_ms = int((time.monotonic() - started) * 1000)

        if 300 <= response.status_code < 400:
            # Redirects are never followed (follow_redirects=False above) —
            # a redirect response lands here as a plain non-2xx result, and
            # is treated as a permanent failure: a receiver that redirects
            # is misconfigured, and following it would re-open the exact
            # SSRF window this connector otherwise closes.
            return DeliveryOutcome(
                status=DeliveryAttemptStatus.PERMANENT_FAILURE,
                http_status_code=response.status_code,
                error_summary="Receiver returned a redirect, which is not followed.",
                duration_ms=duration_ms,
            )
        if response.status_code < 300:
            return DeliveryOutcome(
                status=DeliveryAttemptStatus.SUCCESS,
                http_status_code=response.status_code,
                error_summary=None,
                duration_ms=duration_ms,
            )
        if response.status_code in (408, 429) or response.status_code >= 500:
            return DeliveryOutcome(
                status=DeliveryAttemptStatus.RETRYABLE_FAILURE,
                http_status_code=response.status_code,
                error_summary=f"Receiver returned HTTP {response.status_code}.",
                duration_ms=duration_ms,
            )
        return DeliveryOutcome(
            status=DeliveryAttemptStatus.PERMANENT_FAILURE,
            http_status_code=response.status_code,
            error_summary=f"Receiver returned HTTP {response.status_code}.",
            duration_ms=duration_ms,
        )
