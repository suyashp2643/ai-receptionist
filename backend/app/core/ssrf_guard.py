"""Destination-URL validation for outbound webhook connectors (Phase 8).

An owner/admin-configured webhook URL is attacker-adjacent input: whatever
this application can reach, a malicious tenant admin can potentially probe
via a "webhook" pointed at an internal service, a cloud metadata endpoint,
or a loopback-bound admin port. This module is the single place that
decides whether a destination is safe to connect to — every connector
that makes an outbound HTTP call MUST validate through here, both when a
connection is saved AND again immediately before every actual delivery
attempt (DNS can change between the two).

Policy (see docs/security.md's Phase 8 threat model for the full writeup):
  - https:// is always permitted (subject to the checks below).
  - http:// is permitted ONLY when every resolved address is a loopback
    address AND Settings.integration_allow_http_for_loopback is true —
    i.e. local development pointed at 127.0.0.1/::1, never anything else.
  - No embedded userinfo (`https://user:pass@host/...`).
  - No scheme other than http/https.
  - Every DNS-resolved address (IPv4 and IPv6) is checked against
    loopback/link-local/private/reserved/multicast/unspecified ranges via
    Python's `ipaddress` module — not a hand-rolled range table.
  - Hostnames are lowercased and a trailing dot is stripped before
    resolution, so `Example.com.` and `example.com` are treated
    identically (DNS treats them identically; a naive string check would
    not).
  - Port 0 is rejected; otherwise no port restriction (a local-dev
    receiver commonly runs on a non-standard port).

This module only validates — it does not, by itself, guarantee the
eventual HTTP connection actually uses the address it validated. That
guarantee is `app/integrations/pinned_transport.py`'s job:
`WebhookConnector.deliver()` calls this function immediately before every
delivery attempt and then forces the TCP connection to
`ValidatedDestination.resolved_ips[0]` via a pinned `httpcore` network
backend, rather than trusting httpx/httpcore's own independent DNS
resolution at connect time — see that module's docstring for the
httpcore-level proof (TLS SNI and certificate hostname verification are
derived from the original request host, never from what the pinned
backend actually dials, so pinning never weakens TLS). Together this
closes the classic TOCTOU/DNS-rebinding gap for every real delivery
attempt: each attempt (including every retry) re-resolves, re-validates,
and re-pins from scratch, so a hostname that starts resolving to a
forbidden address is caught on the very next attempt, with no window for
a second, different DNS answer to be substituted between this function's
own validation and the connection it guards. See docs/security.md's
Phase 8 section for the full write-up, including the one residual
limitation this cannot address (a DNS response that is itself already
compromised at the exact moment `socket.getaddrinfo` is called here).
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.config import Settings

_ALLOWED_SCHEMES = frozenset({"http", "https"})


class DestinationValidationError(ValueError):
    """Raised with a message safe to show to the AUTHENTICATED owner/admin
    configuring the connector (they already control this tenant's
    configuration) — never propagated to an unauthenticated caller or a
    generic delivery-failure surface. See callers for where this boundary
    is enforced."""


@dataclass(frozen=True)
class ValidatedDestination:
    url: str
    hostname: str
    port: int
    scheme: str
    resolved_ips: tuple[str, ...]


def _normalize_hostname(hostname: str) -> str:
    return hostname.lower().rstrip(".")


def _is_forbidden_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, *, allow_loopback: bool) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        # An IPv4-mapped IPv6 address (::ffff:a.b.c.d) represents plain
        # IPv4 a.b.c.d wearing an IPv6 wrapper. Python's ipaddress module
        # marks the ENTIRE ::ffff:0:0/96 notation `is_reserved = True`
        # unconditionally, regardless of what it maps to — checked live:
        # `ipaddress.ip_address("::ffff:93.184.216.34").is_reserved` is
        # True even though 93.184.216.34 itself is an ordinary public
        # address. Classify by the unwrapped address alone (recursing
        # once) rather than also applying the wrapper's own always-True
        # is_reserved flag, so a legitimate public destination that
        # happens to arrive in mapped form is not rejected — while a
        # mapped *private* address is still caught, via the exact same
        # recursive check applied to the unwrapped IPv4 address.
        return _is_forbidden_ip(ip.ipv4_mapped, allow_loopback=allow_loopback)
    if ip.is_loopback:
        return not allow_loopback
    return bool(ip.is_link_local or ip.is_private or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def validate_destination_url(url: str, *, settings: Settings) -> ValidatedDestination:
    """Raises DestinationValidationError for anything unsafe. Returns the
    resolved, validated destination otherwise — callers should re-run this
    immediately before each delivery attempt, not cache the result
    indefinitely."""
    if not url or len(url) > 2048:
        raise DestinationValidationError("Destination URL is missing or too long.")

    parts = urlsplit(url)

    if parts.scheme not in _ALLOWED_SCHEMES:
        raise DestinationValidationError("Destination URL must use http:// or https://.")

    if parts.username is not None or parts.password is not None:
        raise DestinationValidationError("Destination URL must not contain embedded credentials.")

    if not parts.hostname:
        raise DestinationValidationError("Destination URL must include a hostname.")

    hostname = _normalize_hostname(parts.hostname)
    port = parts.port if parts.port is not None else (443 if parts.scheme == "https" else 80)
    if port == 0:
        raise DestinationValidationError("Destination URL port 0 is not permitted.")

    try:
        addr_infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise DestinationValidationError("Destination hostname could not be resolved.") from exc

    resolved_ips: list[str] = []
    for _family, _type, _proto, _canonname, sockaddr in addr_infos:
        raw_ip = sockaddr[0]
        try:
            ip = ipaddress.ip_address(raw_ip)
        except ValueError:
            continue
        resolved_ips.append(str(ip))

    if not resolved_ips:
        raise DestinationValidationError("Destination hostname did not resolve to any address.")

    all_loopback = all(ipaddress.ip_address(ip).is_loopback for ip in resolved_ips)
    allow_http = parts.scheme == "http" and settings.integration_allow_http_for_loopback and all_loopback
    if parts.scheme == "http" and not allow_http:
        raise DestinationValidationError(
            "Plain http:// is only permitted for a loopback destination in local development."
        )

    # Loopback is only ever permitted via the http+dev-flag exception above —
    # an https:// destination that happens to resolve to loopback gets no
    # special treatment, so production policy is never weakened by a target
    # merely choosing TLS.
    for ip_str in resolved_ips:
        ip = ipaddress.ip_address(ip_str)
        if _is_forbidden_ip(ip, allow_loopback=allow_http):
            raise DestinationValidationError(
                "Destination resolves to an address that is not permitted "
                "(loopback/link-local/private/reserved/multicast/unspecified)."
            )

    return ValidatedDestination(
        url=url, hostname=hostname, port=port, scheme=parts.scheme, resolved_ips=tuple(resolved_ips)
    )
