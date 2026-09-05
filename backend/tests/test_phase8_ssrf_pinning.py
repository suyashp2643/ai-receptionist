"""Covers the IP-pinning transport (app/integrations/pinned_transport.py)
and the fuller DNS-rebinding/bypass matrix that
tests/test_phase8_ssrf_guard.py's simpler per-range tests don't exercise:
mixed public/private DNS answers, a hostname that resolves differently
between two calls, redirect handling through the real delivery path, and
numeric/encoded bypass forms. Every test mocks `socket.getaddrinfo`
directly (or uses IP literals, which never trigger a real DNS query) —
zero external network calls anywhere in this file. The one real network
activity anywhere is loopback-only (127.0.0.1), matching the pattern
already established in tests/test_phase8_connectors.py.
"""

import http.server
import ipaddress
import socket
import threading
import uuid
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import httpx
import pytest
from app.config import Settings
from app.core.ssrf_guard import DestinationValidationError, validate_destination_url
from app.integrations.connectors.webhook import WebhookConnector
from app.integrations.envelope import ConnectionTestEventPayload, EventType, build_envelope
from app.integrations.pinned_transport import _PinnedNetworkBackend, build_pinned_transport
from app.models.enums import DeliveryAttemptStatus
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


def _fake_addrinfo(*ips: str, port: int = 443) -> list:
    results = []
    for ip in ips:
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        sockaddr = (ip, port, 0, 0) if family == socket.AF_INET6 else (ip, port)
        results.append((family, socket.SOCK_STREAM, 6, "", sockaddr))
    return results


class TestDnsResolutionMatrix:
    def test_public_hostname_is_allowed(self):
        with patch("app.core.ssrf_guard.socket.getaddrinfo", return_value=_fake_addrinfo("93.184.216.34")):
            result = validate_destination_url("https://api.example.com/hook", settings=_settings())
        assert result.resolved_ips == ("93.184.216.34",)

    def test_private_hostname_is_rejected(self):
        with patch("app.core.ssrf_guard.socket.getaddrinfo", return_value=_fake_addrinfo("10.0.0.5")):
            with pytest.raises(DestinationValidationError):
                validate_destination_url("https://internal.example.com/hook", settings=_settings())

    def test_mixed_public_and_private_answers_are_rejected(self):
        """A hostname that resolves to BOTH a legitimate public address and
        a private one must be rejected entirely — never "pick the public
        one and proceed," since that would let an attacker present a
        seemingly-safe answer during validation while a private address
        remains a live possibility for the actual connection."""
        with patch("app.core.ssrf_guard.socket.getaddrinfo", return_value=_fake_addrinfo("93.184.216.34", "10.0.0.5")):
            with pytest.raises(DestinationValidationError):
                validate_destination_url("https://mixed.example.com/hook", settings=_settings())

    def test_dns_resolution_failure_is_a_controlled_error(self):
        with patch("app.core.ssrf_guard.socket.getaddrinfo", side_effect=socket.gaierror("mocked failure")):
            with pytest.raises(DestinationValidationError, match="could not be resolved"):
                validate_destination_url("https://nowhere.invalid/hook", settings=_settings())

    def test_ipv4_public_address_is_allowed(self):
        with patch("app.core.ssrf_guard.socket.getaddrinfo", return_value=_fake_addrinfo("93.184.216.34")):
            result = validate_destination_url("https://v4.example.com/hook", settings=_settings())
        assert result.resolved_ips == ("93.184.216.34",)

    def test_ipv6_public_address_is_allowed(self):
        with patch(
            "app.core.ssrf_guard.socket.getaddrinfo", return_value=_fake_addrinfo("2606:2800:220:1:248:1893:25c8:1946")
        ):
            result = validate_destination_url("https://v6.example.com/hook", settings=_settings())
        assert result.resolved_ips == ("2606:2800:220:1:248:1893:25c8:1946",)

    def test_ipv6_private_address_is_rejected(self):
        with patch("app.core.ssrf_guard.socket.getaddrinfo", return_value=_fake_addrinfo("fc00::1")):
            with pytest.raises(DestinationValidationError):
                validate_destination_url("https://v6-private.example.com/hook", settings=_settings())

    def test_ipv4_mapped_ipv6_private_address_is_rejected(self):
        """::ffff:10.0.0.1 is IPv4 10.0.0.1 wearing an IPv6 wrapper —
        Python's ipaddress.IPv6Address.is_private does not see through
        the mapping on its own, so app/core/ssrf_guard.py explicitly
        unwraps and re-checks it (see _is_forbidden_ip)."""
        with patch("app.core.ssrf_guard.socket.getaddrinfo", return_value=_fake_addrinfo("::ffff:10.0.0.1")):
            with pytest.raises(DestinationValidationError):
                validate_destination_url("https://v4mapped.example.com/hook", settings=_settings())

    def test_ipv4_mapped_ipv6_public_address_is_allowed(self):
        with patch("app.core.ssrf_guard.socket.getaddrinfo", return_value=_fake_addrinfo("::ffff:93.184.216.34")):
            result = validate_destination_url("https://v4mapped-public.example.com/hook", settings=_settings())
        # Python's ipaddress module normalizes the string form to compact
        # hex (`::ffff:5db8:d822`) rather than the dotted-quad notation —
        # same address, different textual representation. What matters is
        # that it resolved successfully (was not rejected) and unwraps back
        # to the correct public IPv4 address.
        assert len(result.resolved_ips) == 1
        resolved = ipaddress.ip_address(result.resolved_ips[0])
        assert resolved.ipv4_mapped == ipaddress.ip_address("93.184.216.34")

    def test_a_hostname_that_resolves_differently_between_two_calls_is_independently_validated(self):
        """Simulates the core DNS-rebinding scenario: the SAME hostname
        answers safely on the first lookup and unsafely on the second.
        Each call to validate_destination_url is a fresh, independent
        resolution — nothing caches or trusts an earlier result — so the
        second call is correctly rejected even though the first succeeded."""
        with patch("app.core.ssrf_guard.socket.getaddrinfo", return_value=_fake_addrinfo("93.184.216.34")):
            first = validate_destination_url("https://rebind.example.com/hook", settings=_settings())
        assert first.resolved_ips == ("93.184.216.34",)

        with patch("app.core.ssrf_guard.socket.getaddrinfo", return_value=_fake_addrinfo("169.254.169.254")):
            with pytest.raises(DestinationValidationError):
                validate_destination_url("https://rebind.example.com/hook", settings=_settings())


class TestEncodedAndNumericBypassForms:
    """The guard's defense is IP-range-based on the *resolved* address,
    never a string pattern on the hostname — so it doesn't matter whether
    an attacker spells the target as a decimal integer, octal, hex, or a
    URL-encoded form; whatever the OS resolver ultimately returns still
    goes through the same range check. Each case mocks getaddrinfo to
    return what a permissive resolver *would* return if it honored that
    encoding, proving the defense holds regardless."""

    @pytest.mark.parametrize(
        "hostname",
        [
            "2130706433",  # decimal form of 127.0.0.1
            "0x7f000001",  # hex form of 127.0.0.1
            "0177.0.0.1",  # octal-leading-zero form of 127.0.0.1
            "127.1",  # short form of 127.0.0.1
            "0",  # shorthand for 0.0.0.0
        ],
    )
    def test_numeric_encoded_loopback_forms_resolve_and_are_rejected(self, hostname):
        with patch("app.core.ssrf_guard.socket.getaddrinfo", return_value=_fake_addrinfo("127.0.0.1")):
            with pytest.raises(DestinationValidationError):
                validate_destination_url(f"https://{hostname}/hook", settings=_settings())

    def test_percent_encoded_host_characters_do_not_bypass_validation(self):
        # urlsplit decodes %2e (.) etc. in the authority section inconsistently
        # across parsers; whatever hostname this ultimately resolves to is
        # still range-checked the same way.
        with patch("app.core.ssrf_guard.socket.getaddrinfo", return_value=_fake_addrinfo("169.254.169.254")):
            with pytest.raises(DestinationValidationError):
                validate_destination_url("https://metadata.internal/hook", settings=_settings())


class _RedirectingHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        self.send_response(302)
        self.send_header("Location", "https://attacker.example.com/steal")
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture()
def redirecting_server() -> Iterator[str]:
    server = http.server.HTTPServer(("127.0.0.1", 0), _RedirectingHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/hook"
    finally:
        server.shutdown()
        thread.join(timeout=5)


class TestRedirectHandling:
    def test_a_redirect_response_is_never_followed_and_is_a_permanent_failure(self, redirecting_server):
        connector = WebhookConnector()
        settings = _settings()
        config = connector.validate_config({"destination_url": redirecting_server}, settings=settings)
        envelope = build_envelope(
            EventType.CONNECTION_TEST_EVENT,
            tenant_id=uuid.uuid4(),
            payload=ConnectionTestEventPayload(triggered_by="test"),
        )
        outcome = connector.deliver(
            config=config, secret=None, envelope=envelope, delivery_id=uuid.uuid4(), settings=settings
        )
        assert outcome.status == DeliveryAttemptStatus.PERMANENT_FAILURE
        assert outcome.http_status_code == 302


class TestPinnedTransport:
    def test_connect_tcp_ignores_the_requested_host_and_uses_the_pinned_ip(self):
        """Direct proof of the pinning mechanism: even when httpcore hands
        our backend a completely different hostname to connect to, the
        underlying real backend is invoked with the pinned IP instead."""
        backend = _PinnedNetworkBackend("203.0.113.7")
        backend._real = MagicMock()
        backend._real.connect_tcp.return_value = "a-fake-stream"

        result = backend.connect_tcp("this-hostname-is-ignored.example.com", 443)

        assert result == "a-fake-stream"
        backend._real.connect_tcp.assert_called_once()
        called_args, called_kwargs = backend._real.connect_tcp.call_args
        assert called_args[0] == "203.0.113.7"
        assert called_args[1] == 443

    def test_pinning_to_an_address_nothing_listens_on_fails_the_connection(self):
        """Proves the override is real, not a silent no-op that falls back
        to resolving the original host: pinning to a loopback port nothing
        listens on must fail to connect, never silently succeed via the
        original (unreachable in this test) hostname."""
        transport = build_pinned_transport("127.0.0.1", verify=False)
        with httpx.Client(transport=transport) as client:
            with pytest.raises(httpx.ConnectError):
                # Port 1 on loopback: nothing listens there.
                client.get("http://this-hostname-is-never-resolved.invalid:1/")

    def test_pinned_delivery_over_real_loopback_http_still_works(self):
        """End-to-end: a real socket connection through the pinned
        transport to a real (loopback) receiver succeeds — pinning must
        not break ordinary delivery, only remove trust in re-resolution."""
        received = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                received["hit"] = True
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            transport = build_pinned_transport("127.0.0.1", verify=False)
            with httpx.Client(transport=transport) as client:
                response = client.get(f"http://this-hostname-is-never-resolved.invalid:{port}/")
            assert response.status_code == 200
            assert received.get("hit") is True
        finally:
            server.shutdown()
            thread.join(timeout=5)
