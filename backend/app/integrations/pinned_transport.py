"""Closes the TOCTOU/DNS-rebinding gap between
app/core/ssrf_guard.py's destination validation and the actual outbound
HTTP connection, by forcing the TCP connection to the exact IP address
that was already resolved and validated — rather than letting the HTTP
client re-resolve the hostname itself (which is what left the gap open;
see the "Known limitation" this module removes in
docs/integration-contracts.md's history).

How this works, precisely, and why it is safe:

httpcore's `HTTPConnection._connect` (the code paths every httpx request
goes through) calls `network_backend.connect_tcp(host=origin_host, ...)`
using the ORIGINAL request hostname — then, entirely separately, calls
`stream.start_tls(ssl_context, server_hostname=origin_host)` for TLS.
Critically, `server_hostname` (which drives both the TLS SNI extension
AND certificate hostname verification) is derived from the request's own
origin host, **never from whatever the network backend actually
connected to**. This is verified against the installed httpcore version
in `tests/test_phase8_ssrf_pinning.py` by asserting the real TLS
handshake still validates the real hostname's certificate even though
the TCP socket was forced elsewhere.

`_PinnedNetworkBackend` below is a `httpcore.NetworkBackend` (the same
public extension point `httpcore.ConnectionPool(network_backend=...)`
takes) whose `connect_tcp` ignores the hostname httpcore hands it and
dials the pre-validated IP literal instead — TLS verification and the
HTTP `Host` header are completely unaffected, since neither is derived
from the backend's connection target.

Residual limitation, stated plainly: this closes the gap between
`ssrf_guard`'s validation and *this* delivery attempt's connection —
each delivery attempt (including every retry) re-resolves, re-validates,
and re-pins independently, so a hostname that starts resolving to a
forbidden address is caught on the very next attempt. It does not, and
cannot, protect against a DNS response that itself lies within the
single resolution `ssrf_guard.validate_destination_url` performs (i.e. if
the authoritative DNS answer at the moment of validation is itself
already the attacker's chosen address, validation correctly rejects it;
if it is not, pinning guarantees the connection uses exactly what was
validated, with no window for a second, different answer to sneak in
between validation and connection).
"""

from __future__ import annotations

import ssl
import typing

import httpcore
import httpx


class _PinnedNetworkBackend(httpcore.NetworkBackend):
    def __init__(self, pinned_ip: str) -> None:
        self._pinned_ip = pinned_ip
        self._real = httpcore.SyncBackend()

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: typing.Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        # `host` is always the original request hostname here — httpcore
        # never resolves it before calling this method; deliberately
        # ignored in favor of the address app/core/ssrf_guard.py already
        # resolved and validated.
        return self._real.connect_tcp(
            self._pinned_ip,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: typing.Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        raise NotImplementedError("Unix sockets are never used for outbound webhook delivery.")

    def sleep(self, seconds: float) -> None:
        self._real.sleep(seconds)


def build_pinned_transport(pinned_ip: str, *, verify: bool | ssl.SSLContext = True) -> httpx.HTTPTransport:
    """Returns an `httpx.HTTPTransport` whose every connection is forced
    to `pinned_ip`, regardless of what hostname the request URL names.
    Use exactly once per delivery attempt, built from that attempt's own
    fresh `validate_destination_url(...).resolved_ips[0]` — never cached
    or reused across attempts, so a retry re-validates and re-pins from
    scratch."""
    ssl_context = verify if isinstance(verify, ssl.SSLContext) else httpx.create_ssl_context(verify=verify)
    transport = httpx.HTTPTransport()
    # httpx.HTTPTransport's own constructor has no public parameter for a
    # custom network_backend (only httpcore.ConnectionPool itself exposes
    # that) — every other transport behavior (timeouts, HTTP/1.1-only,
    # connection limits) is left at httpx's own defaults by replacing only
    # the pool, not reimplementing HTTPTransport.
    transport._pool = httpcore.ConnectionPool(
        ssl_context=ssl_context,
        network_backend=_PinnedNetworkBackend(pinned_ip),
    )
    return transport
