"""Privacy-conscious client identification for the public widget's rate
limiter. Never used for anything security-critical on its own (an IP is
trivially spoofable/shared) — only as one input to abuse-reduction rate
limiting, alongside the widget installation id and action type."""

import hashlib

from fastapi import Request


def get_client_ip(request: Request, *, trust_proxy_headers: bool) -> str:
    """`trust_proxy_headers` must only be enabled when the app is actually
    deployed behind a proxy that sets `X-Forwarded-For` itself and strips
    any client-supplied one — otherwise any visitor can forge this header
    to make every request appear to come from a different IP, defeating
    the rate limiter entirely. Phase 5 defaults this to False."""
    if trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def hash_client_ip(ip: str) -> str:
    """Truncated hash, not the raw IP: rate-limit bucket keys are held in
    process memory for the duration of a window, and there is no reason to
    keep a reversible record of a visitor's address even transiently."""
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:16]
