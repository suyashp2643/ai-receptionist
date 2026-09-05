"""Deliberately never resolves a real external hostname (e.g. example.com)
— every test either uses an IP literal (getaddrinfo resolves those purely
locally, no network round-trip) or mocks `socket.getaddrinfo` directly, so
this suite makes zero real network/DNS calls, matching Phase 8's "no
external network contact during testing" constraint.
"""

import socket
from unittest.mock import patch

import pytest
from app.config import Settings
from app.core.ssrf_guard import DestinationValidationError, validate_destination_url


def _settings(**overrides) -> Settings:
    defaults = {"integration_allow_http_for_loopback": True}
    defaults.update(overrides)
    return Settings(**defaults)


def _fake_addrinfo(ip: str):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]


class TestSchemePolicy:
    def test_https_to_a_public_host_is_allowed(self):
        with patch("app.core.ssrf_guard.socket.getaddrinfo", return_value=_fake_addrinfo("93.184.216.34")):
            result = validate_destination_url("https://example.com/hook", settings=_settings())
        assert result.scheme == "https"

    def test_ftp_scheme_is_rejected(self):
        with pytest.raises(DestinationValidationError):
            validate_destination_url("ftp://example.com/hook", settings=_settings())

    def test_file_scheme_is_rejected(self):
        with pytest.raises(DestinationValidationError):
            validate_destination_url("file:///etc/passwd", settings=_settings())

    def test_http_to_a_public_host_is_rejected(self):
        with pytest.raises(DestinationValidationError, match="loopback destination in local development"):
            validate_destination_url("http://example.com/hook", settings=_settings())

    def test_http_to_loopback_is_allowed_when_dev_flag_is_set(self):
        result = validate_destination_url("http://127.0.0.1:9000/hook", settings=_settings())
        assert result.resolved_ips == ("127.0.0.1",)

    def test_http_to_loopback_is_rejected_when_dev_flag_is_off(self):
        with pytest.raises(DestinationValidationError):
            validate_destination_url(
                "http://127.0.0.1:9000/hook", settings=_settings(integration_allow_http_for_loopback=False)
            )

    def test_https_to_loopback_is_never_allowed_even_with_dev_flag(self):
        """https:// choosing loopback gets no special treatment — the dev
        exception is keyed off scheme=http specifically, not "any loopback
        request", so production policy is never weakened by a target
        merely using TLS."""
        with pytest.raises(DestinationValidationError):
            validate_destination_url("https://127.0.0.1:9443/hook", settings=_settings())


class TestEmbeddedCredentials:
    def test_userinfo_in_the_url_is_rejected(self):
        with pytest.raises(DestinationValidationError, match="embedded credentials"):
            validate_destination_url("https://user:pass@127.0.0.1/hook", settings=_settings())


class TestPrivateAndReservedRanges:
    @pytest.mark.parametrize(
        "url",
        [
            "https://169.254.169.254/latest/meta-data/",  # cloud metadata
            "https://10.0.0.5/hook",  # RFC1918 private
            "https://172.16.0.5/hook",  # RFC1918 private
            "https://192.168.1.5/hook",  # RFC1918 private
            "https://224.0.0.1/hook",  # multicast
            "https://0.0.0.0/hook",  # unspecified
            "https://[::1]/hook",  # IPv6 loopback
            "https://[fe80::1]/hook",  # IPv6 link-local
            "https://[fc00::1]/hook",  # IPv6 unique local (private)
        ],
    )
    def test_unsafe_destination_is_rejected(self, url):
        with pytest.raises(DestinationValidationError):
            validate_destination_url(url, settings=_settings())

    def test_public_ip_literal_is_allowed(self):
        # An IP literal is resolved purely locally by getaddrinfo (no real
        # DNS round-trip) — this proves the guard doesn't reject every raw
        # IP, just unsafe ranges.
        result = validate_destination_url("https://93.184.216.34/hook", settings=_settings())
        assert result.resolved_ips == ("93.184.216.34",)


class TestMalformedInput:
    def test_empty_url_is_rejected(self):
        with pytest.raises(DestinationValidationError):
            validate_destination_url("", settings=_settings())

    def test_missing_hostname_is_rejected(self):
        with pytest.raises(DestinationValidationError):
            validate_destination_url("https:///hook", settings=_settings())

    def test_unresolvable_hostname_is_rejected(self):
        with patch("app.core.ssrf_guard.socket.getaddrinfo", side_effect=socket.gaierror("mocked failure")):
            with pytest.raises(DestinationValidationError, match="could not be resolved"):
                validate_destination_url("https://this-host-does-not-exist.invalid/hook", settings=_settings())

    def test_port_zero_is_rejected(self):
        with pytest.raises(DestinationValidationError, match="port 0"):
            validate_destination_url("https://127.0.0.1:0/hook", settings=_settings())

    def test_overlong_url_is_rejected(self):
        with pytest.raises(DestinationValidationError):
            validate_destination_url("https://127.0.0.1/" + "a" * 3000, settings=_settings())


class TestHostnameNormalization:
    def test_trailing_dot_and_case_are_normalized(self):
        with patch("app.core.ssrf_guard.socket.getaddrinfo", return_value=_fake_addrinfo("93.184.216.34")) as mocked:
            result = validate_destination_url("https://Example.com./hook", settings=_settings())
        assert result.hostname == "example.com"
        mocked.assert_called_once()
        assert mocked.call_args.args[0] == "example.com"
