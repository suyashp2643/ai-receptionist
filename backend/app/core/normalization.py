def normalize_email(email: str) -> str:
    """Simple, consistent normalization: trim whitespace, lowercase the whole
    address. Deliberately not attempting provider-specific rules (e.g. Gmail
    dot-insensitivity) — those are provider policy, not RFC-guaranteed, and
    "consistent" matters more here than "maximally deduplicated"."""
    return email.strip().lower()
