import re


def normalize_email(email: str) -> str:
    """Simple, consistent normalization: trim whitespace, lowercase the whole
    address. Deliberately not attempting provider-specific rules (e.g. Gmail
    dot-insensitivity) — those are provider policy, not RFC-guaranteed, and
    "consistent" matters more here than "maximally deduplicated"."""
    return email.strip().lower()


def normalize_phone(phone: str) -> str:
    """Strips everything to digits and re-adds a single leading `+` if the
    original had one. Deliberately not full E.164 validation/parsing (no
    `phonenumbers` dependency for Phase 5's zero-cost scope) — this only
    makes dedup and storage consistent, it does not assert the number is
    dialable or real."""
    stripped = phone.strip()
    leading_plus = stripped.startswith("+")
    digits = re.sub(r"\D", "", stripped)
    return f"+{digits}" if leading_plus and digits else digits
