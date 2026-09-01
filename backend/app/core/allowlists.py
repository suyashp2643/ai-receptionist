"""Server-maintained allow-lists. Never accept these values as free text from
a client — every place that stores one of these must validate against the
corresponding set here, so the allow-list itself is the single source of
truth (no scattered industry-specific if/else, no client-supplied code)."""

# --- Enabled actions (Phase 3 stores configuration only; nothing executes) ---
ALLOWED_ACTIONS: frozenset[str] = frozenset(
    {
        "answer_questions",
        "capture_contact",
        "qualify_lead",
        "request_callback",
        "request_appointment",
        "request_viewing",
        "request_reservation",
        "request_demo",
        "request_test_drive",
        "request_service_visit",
        "request_human_handoff",
    }
)

# --- Qualification field types ---
QUALIFICATION_FIELD_TYPES: frozenset[str] = frozenset(
    {
        "short_text",
        "long_text",
        "email",
        "phone",
        "number",
        "currency",
        "date",
        "time",
        "datetime",
        "boolean",
        "single_select",
        "multi_select",
    }
)

SELECT_FIELD_TYPES: frozenset[str] = frozenset({"single_select", "multi_select"})

# --- Qualification rule types (declarative only — no expression language) ---
QUALIFICATION_RULE_TYPES: frozenset[str] = frozenset(
    {
        "required_fields_completed",
        "equals",
        "one_of",
        "numeric_min",
        "numeric_max",
        "consent_required",
    }
)

# --- Supported language codes (ISO 639-1, curated subset) ---
SUPPORTED_LANGUAGE_CODES: frozenset[str] = frozenset(
    {
        "en",
        "es",
        "fr",
        "de",
        "it",
        "pt",
        "nl",
        "pl",
        "sv",
        "hi",
        "ar",
        "zh",
        "ja",
        "ko",
        "ru",
        "tr",
    }
)

# --- Mandatory safety rules that a tenant cannot remove for certain templates ---
# Keyed by IndustryTemplate.key. Enforced by the receptionist workflow service
# whenever the template's key matches, regardless of which template *version*
# is in play.
MANDATORY_SAFETY_RULES: dict[str, tuple[str, ...]] = {
    "clinic": (
        "Administrative intake only — this assistant does not provide medical advice.",
        "Do not diagnose any condition.",
        "Do not prescribe or recommend medication.",
        "Do not give emergency medical advice.",
        "Direct urgent or life-threatening cases to local emergency services immediately.",
    ),
    "law_firm": (
        "Administrative intake only — this assistant does not provide legal advice.",
        "Do not give definitive legal advice.",
        "Do not promise any outcome for a legal matter.",
        "Recommend human consultation with a qualified attorney when appropriate.",
    ),
}

# --- Recommended tone options (validated but not a rigid DB enum, so new
# tones don't require a migration) ---
SUGGESTED_TONES: frozenset[str] = frozenset({"friendly", "professional", "warm", "formal", "casual", "empathetic"})
