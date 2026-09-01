"""Plain-text safety helpers shared by every Phase 3 schema that stores
tenant-authored text (business profile fields, receptionist copy, FAQs,
knowledge documents, qualification labels, etc.).

Policy: these fields are plain text, full stop. Rather than pulling in an
HTML-sanitization dependency and trying to allow a "safe subset" of markup
(a well-known source of bypass bugs), any `<`/`>` character is rejected
outright. This is simple, deterministic, and needs no new dependency.
"""

import re

_ANGLE_BRACKETS = re.compile(r"[<>]")

# Reasonable, generous limits — enforced everywhere text is stored so a
# single tenant can't store unbounded JSONB blobs or knowledge text.
MAX_SHORT_TEXT = 200
MAX_MEDIUM_TEXT = 1_000
MAX_LONG_TEXT = 5_000
MAX_KNOWLEDGE_TEXT = 200_000  # ~40k words of plain text per document

_PHONE_RE = re.compile(r"^\+?[1-9]\d{6,14}$")
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_SAFE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def reject_html(value: str) -> str:
    if _ANGLE_BRACKETS.search(value):
        raise ValueError("This field must be plain text — angle brackets are not allowed.")
    return value


def validate_plain_text(value: str, *, max_length: int) -> str:
    value = value.strip()
    if not value:
        raise ValueError("This field cannot be empty.")
    if len(value) > max_length:
        raise ValueError(f"This field must be at most {max_length} characters.")
    return reject_html(value)


def validate_optional_plain_text(value: str | None, *, max_length: int) -> str | None:
    if value is None or value == "":
        return None
    return validate_plain_text(value, max_length=max_length)


def validate_phone(value: str) -> str:
    value = value.strip()
    if not _PHONE_RE.match(value):
        raise ValueError("Phone number must be a reasonable international number, e.g. +14155551234.")
    return value


def validate_optional_phone(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return validate_phone(value)


def validate_hex_color(value: str) -> str:
    value = value.strip()
    if not _HEX_COLOR_RE.match(value):
        raise ValueError("Accent color must be a 6-digit hex code, e.g. #1A2B3C.")
    return value


def validate_optional_hex_color(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return validate_hex_color(value)


def validate_time_hhmm(value: str) -> str:
    if not _TIME_RE.match(value):
        raise ValueError("Time must be in 24-hour HH:MM format, e.g. 09:00.")
    return value


def validate_safe_key(value: str) -> str:
    if not _SAFE_KEY_RE.match(value):
        raise ValueError(
            "Key must start with a lowercase letter and contain only lowercase "
            "letters, digits, and underscores (max 64 characters)."
        )
    return value
