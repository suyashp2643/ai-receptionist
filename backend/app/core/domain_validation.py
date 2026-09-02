"""Hostname validation for WidgetInstallation.allowed_domains and Origin
header checks (app/api/v1/widget_public.py). Two independent uses of the
same normalized form:

1. Storage-time validation when a tenant configures allowed domains — must
   reject anything that isn't a bare hostname (no scheme, path, port,
   userinfo, wildcard-as-a-whole-label, or IP literal), so the stored list
   stays a predictable allow-list rather than an arbitrary-string bag.
2. Request-time comparison of an incoming Origin header's hostname against
   that stored list — abuse reduction only, never sole authorization (see
   WidgetVisitorSession for the real authorization boundary).

`www` is handled deliberately: registering `example.com` does NOT
implicitly allow `www.example.com` or vice versa — a tenant must list both
if they serve the widget from both, keeping the allow-list's meaning
literal rather than "clever".
"""

import re

_HOSTNAME_LABEL = r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?"
_HOSTNAME_RE = re.compile(rf"^{_HOSTNAME_LABEL}(\.{_HOSTNAME_LABEL})*$")
_MAX_HOSTNAME_LENGTH = 253

LOCALHOST_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "[::1]"})


class InvalidDomainError(ValueError):
    pass


def normalize_domain(raw: str) -> str:
    """Validates and lowercases a single hostname. Raises InvalidDomainError
    for anything that is not a bare hostname — callers must not pass a URL,
    scheme, path, port, or wildcard segment expecting this to "extract" a
    hostname from it; that permissiveness is exactly what would let an
    unreviewed value slip into an allow-list."""
    if not raw or not isinstance(raw, str):
        raise InvalidDomainError("Domain must be a non-empty string.")

    candidate = raw.strip().lower()

    if candidate in LOCALHOST_HOSTNAMES:
        return candidate

    if "://" in candidate:
        raise InvalidDomainError("Domain must not include a URL scheme.")
    if "/" in candidate or "?" in candidate or "#" in candidate:
        raise InvalidDomainError("Domain must not include a path, query, or fragment.")
    if ":" in candidate:
        raise InvalidDomainError("Domain must not include a port.")
    if "@" in candidate:
        raise InvalidDomainError("Domain must not include userinfo.")
    if "*" in candidate:
        raise InvalidDomainError("Wildcard domains are not supported.")
    if candidate.endswith("."):
        candidate = candidate[:-1]
    if len(candidate) > _MAX_HOSTNAME_LENGTH:
        raise InvalidDomainError("Domain is too long.")
    if not _HOSTNAME_RE.match(candidate):
        raise InvalidDomainError(f"'{raw}' is not a valid hostname.")

    return candidate


def is_localhost(hostname: str) -> bool:
    return hostname in LOCALHOST_HOSTNAMES


def hostname_matches_allowed_domains(hostname: str, allowed_domains: list[str]) -> bool:
    """Exact match only — no implicit subdomain or www expansion. `hostname`
    should already be normalized (e.g. via `extract_origin_hostname`)."""
    return hostname in allowed_domains


def extract_origin_hostname(origin: str) -> str | None:
    """Parses a browser `Origin` header (e.g. `https://example.com:443`) down
    to its lowercased hostname, or None if the header is missing/malformed.
    Deliberately tolerant of a trailing port here (unlike normalize_domain,
    which forbids one in stored config) since the browser always includes
    one where applicable — the port itself is not compared."""
    if not origin:
        return None
    match = re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://([^/]+)$", origin.strip())
    if not match:
        return None
    host_and_port = match.group(1).lower()
    if host_and_port.startswith("["):
        # IPv6 literal, e.g. [::1]:3000
        end = host_and_port.find("]")
        if end == -1:
            return None
        return host_and_port[: end + 1]
    return host_and_port.split(":", 1)[0]
