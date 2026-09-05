"""Phase 8 secret handling: inbound API keys (generated, hashed, never
stored in plaintext) and outbound webhook signing secrets (encrypted at
rest with an application-level key). Follows the exact conventions
`app/core/security.py` already established for Phase 2/5's own
high-entropy random tokens — fast SHA-256 for hashing (not Argon2: these
are random tokens, not human passwords, so deliberate slowness buys
nothing), returned to the caller exactly once, only the hash persisted.

Encryption uses `cryptography`'s Fernet — an established, reviewed
authenticated-encryption construct (AES-128-CBC + HMAC-SHA256, per the
library's own specification), not a hand-rolled primitive.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings

_API_KEY_BYTES = 32  # 256 bits of entropy, same as refresh/capability tokens
_API_KEY_DISPLAY_LAST_N = 4


class SecretDecryptionError(Exception):
    """Raised when a stored encrypted secret cannot be decrypted — either
    the encryption key changed without a migration, or the ciphertext was
    corrupted. Never raised for "no secret configured" (that's just
    None) — only for "a secret exists but we can't read it."""


def generate_api_key(*, prefix: str) -> str:
    """Returned to the caller exactly once by the route that creates it —
    see IntegrationConnectionCreated schema. Never persisted; only
    hash_api_key()'s output is stored."""
    return f"{prefix}{secrets.token_urlsafe(_API_KEY_BYTES)}"


def hash_api_key(raw_key: str) -> str:
    """Fast hash is intentional — this is a high-entropy random token, not
    a human password; see app/core/security.py::hash_refresh_token for the
    same reasoning applied to Phase 2/5's own tokens."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def verify_api_key(raw_key: str, *, expected_hash: str) -> bool:
    """Constant-time comparison of the freshly computed hash against the
    stored one — never a raw `==` on secret-derived strings."""
    return hmac.compare_digest(hash_api_key(raw_key), expected_hash)


def api_key_display_metadata(raw_key: str, *, prefix: str) -> tuple[str, str]:
    """Returns (prefix, last_four) for post-creation display — never
    enough to reconstruct the key, only enough for an operator to
    recognize which key is which in a list."""
    without_prefix = raw_key[len(prefix) :] if raw_key.startswith(prefix) else raw_key
    return prefix, without_prefix[-_API_KEY_DISPLAY_LAST_N:]


def _fernet(settings: Settings) -> Fernet:
    key = settings.require_integration_encryption_key()
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        # A configured-but-malformed key must fail loudly and safely, the
        # same as an unconfigured one — never fall back to plaintext.
        raise RuntimeError(
            "INTEGRATION_ENCRYPTION_KEY is set but is not a valid Fernet key. "
            'Generate one with `python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"`.'
        ) from exc


def encrypt_secret(plaintext: str, *, settings: Settings) -> tuple[str, int]:
    """Returns (ciphertext, key_version). Raises RuntimeError (via
    Settings.require_integration_encryption_key) if no encryption key is
    configured — this is the "fail safely, never store plaintext" gate
    required before any connector holding a signing secret can be
    created."""
    token = _fernet(settings).encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8"), settings.integration_encryption_key_version


def decrypt_secret(ciphertext: str, *, key_version: int, settings: Settings) -> str:
    if key_version != settings.integration_encryption_key_version:
        # Multi-key rotation (trying older key versions in turn) is out of
        # scope for Phase 8 — documented as a known limitation. Failing
        # loudly here is safer than silently returning garbage.
        raise SecretDecryptionError(
            f"Secret was encrypted under key version {key_version}, but the "
            f"currently configured key is version {settings.integration_encryption_key_version}."
        )
    try:
        return _fernet(settings).decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise SecretDecryptionError("Stored secret could not be decrypted with the configured key.") from exc


def redact_secret_for_display(raw_or_none: str | None) -> str:
    """Used only in contexts that must NEVER show a real secret value
    (logs, error messages, activity-event metadata) but want to indicate
    presence/absence — e.g. "signing secret: [set]" vs "[not set]"."""
    return "[set]" if raw_or_none else "[not set]"
