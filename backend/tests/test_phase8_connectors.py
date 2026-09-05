"""Connector-level tests. The webhook delivery tests use a real local
HTTP server bound to 127.0.0.1 (loopback only, no external network
contact) — the same pattern verified live during Phase 8 development."""

import http.server
import threading
import uuid
from collections.abc import Iterator

import pytest
from app.config import Settings
from app.integrations.connectors.base import ConnectorConfigError
from app.integrations.connectors.factory import get_connector
from app.integrations.connectors.mock import MockConnector
from app.integrations.connectors.revenue_brain import RevenueBrainConnector
from app.integrations.connectors.sales_employee import ALLOWED_EVENT_TYPES, SalesEmployeeConnector
from app.integrations.connectors.webhook import WebhookConnector
from app.integrations.envelope import ConnectionTestEventPayload, EventType, build_envelope
from app.integrations.signing import (
    HEADER_DELIVERY_ID,
    HEADER_EVENT_ID,
    HEADER_SIGNATURE,
    HEADER_TIMESTAMP,
    verify_signature,
)
from app.models.enums import DeliveryAttemptStatus, IntegrationConnectorType
from cryptography.fernet import Fernet


def _settings(**overrides) -> Settings:
    defaults = {
        "integration_encryption_key": Fernet.generate_key().decode("utf-8"),
        "integration_allow_http_for_loopback": True,
        "integration_delivery_connect_timeout_seconds": 2.0,
        "integration_delivery_read_timeout_seconds": 2.0,
    }
    defaults.update(overrides)
    return Settings(**defaults)


class _RecordingHandler(http.server.BaseHTTPRequestHandler):
    received: list[dict] = []
    response_status = 200

    def do_POST(self):  # noqa: N802 — stdlib handler method name
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.__class__.received.append({"body": body, "headers": dict(self.headers)})
        self.send_response(self.__class__.response_status)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):  # silence stdlib access logging in test output
        pass


@pytest.fixture()
def loopback_server() -> Iterator[tuple[str, list[dict]]]:
    _RecordingHandler.received = []
    _RecordingHandler.response_status = 200
    server = http.server.HTTPServer(("127.0.0.1", 0), _RecordingHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/hook", _RecordingHandler.received
    finally:
        server.shutdown()
        thread.join(timeout=5)


class TestMockConnector:
    def test_success_mode_delivers_successfully(self):
        connector = MockConnector()
        settings = _settings()
        config = connector.validate_config({"mode": "success"}, settings=settings)
        envelope = build_envelope(
            EventType.CONNECTION_TEST_EVENT,
            tenant_id=uuid.uuid4(),
            payload=ConnectionTestEventPayload(triggered_by="test"),
        )
        outcome = connector.deliver(
            config=config, secret=None, envelope=envelope, delivery_id=uuid.uuid4(), settings=settings
        )
        assert outcome.status == DeliveryAttemptStatus.SUCCESS

    def test_failure_mode_is_retryable(self):
        connector = MockConnector()
        settings = _settings()
        config = connector.validate_config({"mode": "failure"}, settings=settings)
        envelope = build_envelope(
            EventType.CONNECTION_TEST_EVENT,
            tenant_id=uuid.uuid4(),
            payload=ConnectionTestEventPayload(triggered_by="test"),
        )
        outcome = connector.deliver(
            config=config, secret=None, envelope=envelope, delivery_id=uuid.uuid4(), settings=settings
        )
        assert outcome.status == DeliveryAttemptStatus.RETRYABLE_FAILURE

    def test_permanent_failure_mode_is_not_retryable(self):
        connector = MockConnector()
        settings = _settings()
        config = connector.validate_config({"mode": "permanent_failure"}, settings=settings)
        envelope = build_envelope(
            EventType.CONNECTION_TEST_EVENT,
            tenant_id=uuid.uuid4(),
            payload=ConnectionTestEventPayload(triggered_by="test"),
        )
        outcome = connector.deliver(
            config=config, secret=None, envelope=envelope, delivery_id=uuid.uuid4(), settings=settings
        )
        assert outcome.status == DeliveryAttemptStatus.PERMANENT_FAILURE

    def test_rejects_an_unknown_mode(self):
        connector = MockConnector()
        with pytest.raises(ConnectorConfigError):
            connector.validate_config({"mode": "not-a-real-mode"}, settings=_settings())


class TestWebhookConnectorDelivery:
    def test_delivers_and_signs_correctly(self, loopback_server):
        url, received = loopback_server
        connector = WebhookConnector()
        settings = _settings()
        config = connector.validate_config({"destination_url": url}, settings=settings)
        secret = "shared-secret"
        envelope = build_envelope(
            EventType.CONNECTION_TEST_EVENT,
            tenant_id=uuid.uuid4(),
            payload=ConnectionTestEventPayload(triggered_by="test"),
        )
        delivery_id = uuid.uuid4()

        outcome = connector.deliver(
            config=config, secret=secret, envelope=envelope, delivery_id=delivery_id, settings=settings
        )

        assert outcome.status == DeliveryAttemptStatus.SUCCESS
        assert len(received) == 1
        headers = received[0]["headers"]
        assert headers[HEADER_DELIVERY_ID] == str(delivery_id)
        assert headers[HEADER_EVENT_ID] == str(envelope.event_id)
        assert verify_signature(
            secret,
            signature=headers[HEADER_SIGNATURE],
            body=received[0]["body"],
            timestamp=headers[HEADER_TIMESTAMP],
            delivery_id=headers[HEADER_DELIVERY_ID],
            event_id=headers[HEADER_EVENT_ID],
            schema_version=str(envelope.event_version),
        )

    def test_field_mapping_is_applied_to_the_delivered_body(self, loopback_server):
        import json

        url, received = loopback_server
        connector = WebhookConnector()
        settings = _settings()
        config = connector.validate_config(
            {
                "destination_url": url,
                "field_mapping": {"rename": {"triggered_by": "source"}, "defaults": {"extra": "x"}},
            },
            settings=settings,
        )
        envelope = build_envelope(
            EventType.CONNECTION_TEST_EVENT,
            tenant_id=uuid.uuid4(),
            payload=ConnectionTestEventPayload(triggered_by="test"),
        )
        connector.deliver(config=config, secret=None, envelope=envelope, delivery_id=uuid.uuid4(), settings=settings)

        sent = json.loads(received[0]["body"])
        assert sent["data"] == {
            "message": "Test event from the AI Receptionist integration lab.",
            "source": "test",
            "extra": "x",
        }

    def test_wrong_secret_fails_signature_verification(self, loopback_server):
        url, received = loopback_server
        connector = WebhookConnector()
        settings = _settings()
        config = connector.validate_config({"destination_url": url}, settings=settings)
        envelope = build_envelope(
            EventType.CONNECTION_TEST_EVENT,
            tenant_id=uuid.uuid4(),
            payload=ConnectionTestEventPayload(triggered_by="test"),
        )
        delivery_id = uuid.uuid4()
        connector.deliver(
            config=config, secret="real-secret", envelope=envelope, delivery_id=delivery_id, settings=settings
        )

        headers = received[0]["headers"]
        assert not verify_signature(
            "wrong-secret",
            signature=headers[HEADER_SIGNATURE],
            body=received[0]["body"],
            timestamp=headers[HEADER_TIMESTAMP],
            delivery_id=headers[HEADER_DELIVERY_ID],
            event_id=headers[HEADER_EVENT_ID],
            schema_version=str(envelope.event_version),
        )

    def test_server_error_is_retryable(self, loopback_server):
        url, _ = loopback_server
        _RecordingHandler.response_status = 503
        connector = WebhookConnector()
        settings = _settings()
        config = connector.validate_config({"destination_url": url}, settings=settings)
        envelope = build_envelope(
            EventType.CONNECTION_TEST_EVENT,
            tenant_id=uuid.uuid4(),
            payload=ConnectionTestEventPayload(triggered_by="test"),
        )
        outcome = connector.deliver(
            config=config, secret=None, envelope=envelope, delivery_id=uuid.uuid4(), settings=settings
        )
        assert outcome.status == DeliveryAttemptStatus.RETRYABLE_FAILURE
        assert outcome.http_status_code == 503

    def test_client_error_is_permanent(self, loopback_server):
        url, _ = loopback_server
        _RecordingHandler.response_status = 400
        connector = WebhookConnector()
        settings = _settings()
        config = connector.validate_config({"destination_url": url}, settings=settings)
        envelope = build_envelope(
            EventType.CONNECTION_TEST_EVENT,
            tenant_id=uuid.uuid4(),
            payload=ConnectionTestEventPayload(triggered_by="test"),
        )
        outcome = connector.deliver(
            config=config, secret=None, envelope=envelope, delivery_id=uuid.uuid4(), settings=settings
        )
        assert outcome.status == DeliveryAttemptStatus.PERMANENT_FAILURE
        assert outcome.http_status_code == 400

    def test_connection_refused_is_retryable(self):
        connector = WebhookConnector()
        settings = _settings()
        # An unused loopback port — nothing is listening, so this must be a
        # connection error, not a hang; still zero external network contact.
        config = connector.validate_config({"destination_url": "http://127.0.0.1:1/hook"}, settings=settings)
        envelope = build_envelope(
            EventType.CONNECTION_TEST_EVENT,
            tenant_id=uuid.uuid4(),
            payload=ConnectionTestEventPayload(triggered_by="test"),
        )
        outcome = connector.deliver(
            config=config, secret=None, envelope=envelope, delivery_id=uuid.uuid4(), settings=settings
        )
        assert outcome.status == DeliveryAttemptStatus.RETRYABLE_FAILURE

    def test_custom_header_allow_list_rejects_disallowed_names(self):
        connector = WebhookConnector()
        with pytest.raises(ConnectorConfigError):
            connector.validate_config(
                {"destination_url": "http://127.0.0.1:9000/hook", "custom_headers": {"Authorization": "Bearer x"}},
                settings=_settings(),
            )

    def test_custom_header_allow_list_accepts_allowed_names(self):
        connector = WebhookConnector()
        config = connector.validate_config(
            {"destination_url": "http://127.0.0.1:9000/hook", "custom_headers": {"X-Api-Key": "abc"}},
            settings=_settings(),
        )
        assert config["custom_headers"] == {"x-api-key": "abc"}


class TestConnectorFactory:
    def test_returns_the_correct_connector_type(self):
        assert isinstance(get_connector(IntegrationConnectorType.MOCK), MockConnector)
        assert isinstance(get_connector(IntegrationConnectorType.WEBHOOK), WebhookConnector)
        assert isinstance(get_connector(IntegrationConnectorType.REVENUE_BRAIN), RevenueBrainConnector)
        assert isinstance(get_connector(IntegrationConnectorType.SALES_EMPLOYEE), SalesEmployeeConnector)

    def test_revenue_brain_requires_a_destination_url(self):
        connector = get_connector(IntegrationConnectorType.REVENUE_BRAIN)
        with pytest.raises(ConnectorConfigError):
            connector.validate_config({}, settings=_settings())

    def test_sales_employee_requires_a_destination_url(self):
        connector = get_connector(IntegrationConnectorType.SALES_EMPLOYEE)
        with pytest.raises(ConnectorConfigError):
            connector.validate_config({}, settings=_settings())


class TestSalesEmployeeEventScope:
    def test_safety_escalation_is_not_in_the_allowed_set(self):
        assert EventType.SAFETY_ESCALATION_DETECTED not in ALLOWED_EVENT_TYPES

    def test_lead_events_are_in_the_allowed_set(self):
        assert EventType.ENQUIRY_QUALIFIED in ALLOWED_EVENT_TYPES
        assert EventType.CONTACT_CAPTURED in ALLOWED_EVENT_TYPES


class TestWebhookFamilyConnectorParity:
    """Phase 8 remediation round: proves every webhook-family connector type
    — not just `WebhookConnector` itself — goes through the identical
    SSRF-validated, pinned-transport delivery path. `RevenueBrainConnector`
    and `SalesEmployeeConnector` subclass `WebhookConnector` and, by
    inspection, never override `deliver` — the tests below turn that
    inspection into an enforced, regression-proof fact rather than an
    assumption a future change could silently invalidate."""

    def test_deliver_is_not_overridden_by_either_subclass(self):
        # Identity, not just equivalence: if either subclass ever gained its
        # own `deliver` (e.g. someone "optimizing" a direct httpx call for
        # one product), this fails immediately and loudly.
        assert RevenueBrainConnector.deliver is WebhookConnector.deliver
        assert SalesEmployeeConnector.deliver is WebhookConnector.deliver

    @pytest.mark.parametrize("connector_cls", [WebhookConnector, RevenueBrainConnector, SalesEmployeeConnector])
    def test_each_connector_type_delivers_successfully_over_the_pinned_transport(self, connector_cls, loopback_server):
        """End-to-end, not just by inheritance: each connector type
        actually completes a real delivery over loopback — proving the
        pinned transport genuinely works when invoked through that type's
        own `deliver`, not merely that the method object is shared."""
        url, received = loopback_server
        connector = connector_cls()
        settings = _settings()
        config = connector.validate_config({"destination_url": url}, settings=settings)
        envelope = build_envelope(
            EventType.CONNECTION_TEST_EVENT,
            tenant_id=uuid.uuid4(),
            payload=ConnectionTestEventPayload(triggered_by="test"),
        )

        outcome = connector.deliver(
            config=config, secret="shared-secret", envelope=envelope, delivery_id=uuid.uuid4(), settings=settings
        )

        assert outcome.status == DeliveryAttemptStatus.SUCCESS
        assert len(received) == 1

    @pytest.mark.parametrize("connector_cls", [WebhookConnector, RevenueBrainConnector, SalesEmployeeConnector])
    def test_each_connector_type_independently_rejects_a_forbidden_destination_at_delivery_time(self, connector_cls):
        """The SSRF guard is re-checked immediately before every delivery
        attempt (not just at config-save time) for every connector type —
        constructing a config that bypasses `validate_config` (as a
        corrupted/legacy row might) and calling `deliver` directly proves
        `deliver` itself, not just the save-time path, enforces this."""
        connector = connector_cls()
        settings = _settings(integration_allow_http_for_loopback=False)
        # A raw config with a private-network destination, as if it had
        # somehow been persisted before this policy applied — deliver()
        # must not trust it.
        config = {"destination_url": "http://127.0.0.1:1/hook", "custom_headers": {}, "field_mapping": None}
        envelope = build_envelope(
            EventType.CONNECTION_TEST_EVENT,
            tenant_id=uuid.uuid4(),
            payload=ConnectionTestEventPayload(triggered_by="test"),
        )

        outcome = connector.deliver(
            config=config, secret="shared-secret", envelope=envelope, delivery_id=uuid.uuid4(), settings=settings
        )

        assert outcome.status == DeliveryAttemptStatus.PERMANENT_FAILURE
        assert outcome.http_status_code is None  # rejected before any connection was attempted
        assert (
            "not permitted" in (outcome.error_summary or "").lower() or "http" in (outcome.error_summary or "").lower()
        )

    @pytest.mark.parametrize("connector_cls", [WebhookConnector, RevenueBrainConnector, SalesEmployeeConnector])
    def test_each_connector_type_never_follows_a_redirect(self, connector_cls):
        """A receiver that responds with a redirect is a permanent failure
        for every connector type — re-uses the same real-redirect-server
        fixture pattern as TestPinnedTransport in
        test_phase8_ssrf_pinning.py, parametrized across all three types."""
        received: list[dict] = []

        class _RedirectHandler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(length)
                received.append({})
                self.send_response(302)
                self.send_header("Location", "http://127.0.0.1:1/elsewhere")
                self.end_headers()

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), _RedirectHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connector = connector_cls()
            settings = _settings()
            config = connector.validate_config({"destination_url": f"http://127.0.0.1:{port}/hook"}, settings=settings)
            envelope = build_envelope(
                EventType.CONNECTION_TEST_EVENT,
                tenant_id=uuid.uuid4(),
                payload=ConnectionTestEventPayload(triggered_by="test"),
            )
            outcome = connector.deliver(
                config=config, secret="shared-secret", envelope=envelope, delivery_id=uuid.uuid4(), settings=settings
            )
            assert outcome.status == DeliveryAttemptStatus.PERMANENT_FAILURE
            assert outcome.http_status_code == 302
            assert len(received) == 1  # never followed to a second request
        finally:
            server.shutdown()
            thread.join(timeout=5)
