"""Deterministic qualification extraction and validation.

Scoped extraction only — a value is only ever attempted for the ONE field
currently being asked about (the next missing required field, in the
active workflow's schema order), never scanned for across arbitrary
fields in the user's message. This is what prevents "assigning an answer
to a field merely because it appears somewhere in an unrelated sentence."
A small, explicit correction-phrase detector separately allows updating an
already-captured field. Consent (`boolean`) is only ever set from an exact
explicit yes/no phrase — never inferred from context.

This is deliberately not NLP — every pattern below is a documented,
testable regex or exact-match rule. The mock provider (and this module)
never claim to understand free-form language beyond these patterns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from app.ai.providers.base import QualificationFieldSummary, QualificationRejection
from app.core.text_safety import reject_html
from app.schemas.qualification import QualificationField

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"\+?\d[\d\s().-]{6,19}\d")
_PHONE_VALID_RE = re.compile(r"^\+?[1-9]\d{6,14}$")
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_CURRENCY_RE = re.compile(r"[$€£]?\s?(\d[\d,]*(?:\.\d+)?)")
_TIME_12H_RE = re.compile(r"\b(1[0-2]|0?[1-9])(?::([0-5]\d))?\s*(am|pm)\b", re.IGNORECASE)
_TIME_24H_RE = re.compile(r"\b([01]\d|2[0-3]):([0-5]\d)\b")
_DATE_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DATE_SLASH_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")

_CONSENT_YES = frozenset(
    {"yes", "y", "yeah", "yep", "i agree", "i consent", "agreed", "confirm", "confirmed", "sure", "ok", "okay"}
)
_CONSENT_NO = frozenset({"no", "n", "nope", "i do not agree", "i don't agree", "decline", "disagree"})

_CORRECTION_TRIGGERS = ("actually", "correction", "change my", "update my", "no wait", "i meant", "sorry, my")

MAX_SHORT_TEXT_ANSWER = 200
MAX_LONG_TEXT_ANSWER = 2000
MIN_LONG_TEXT_ANSWER = 10


def to_field_summary(field_def: QualificationField) -> QualificationFieldSummary:
    options = [{"value": o.value, "label": o.label} for o in field_def.options] if field_def.options else None
    return QualificationFieldSummary(key=field_def.key, label=field_def.label, type=field_def.type, options=options)


def _normalize_email(raw: str) -> str | None:
    match = _EMAIL_RE.search(raw)
    return match.group(0).lower() if match else None


def _normalize_phone(raw: str) -> str | None:
    match = _PHONE_RE.search(raw)
    if not match:
        return None
    digits = re.sub(r"[^\d+]", "", match.group(0))
    if digits.count("+") > 1:
        digits = "+" + digits.replace("+", "")
    return digits if _PHONE_VALID_RE.match(digits) else None


def _extract_number(raw: str) -> float | None:
    match = _NUMBER_RE.search(raw)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _extract_currency(raw: str) -> float | None:
    match = _CURRENCY_RE.search(raw)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _extract_date(raw: str) -> str | None:
    iso_match = _DATE_ISO_RE.search(raw)
    if iso_match:
        try:
            datetime(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
        except ValueError:
            return None
        return iso_match.group(0)

    slash_match = _DATE_SLASH_RE.search(raw)
    if slash_match:
        month, day, year = int(slash_match.group(1)), int(slash_match.group(2)), int(slash_match.group(3))
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


def _extract_time(raw: str) -> str | None:
    match_24h = _TIME_24H_RE.search(raw)
    if match_24h:
        return match_24h.group(0)

    match_12h = _TIME_12H_RE.search(raw)
    if match_12h:
        hour = int(match_12h.group(1))
        minute = int(match_12h.group(2)) if match_12h.group(2) else 0
        period = match_12h.group(3).lower()
        if period == "pm" and hour != 12:
            hour += 12
        if period == "am" and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute:02d}"
    return None


def _extract_datetime(raw: str) -> str | None:
    date_part = _extract_date(raw)
    time_part = _extract_time(raw)
    return f"{date_part}T{time_part}" if date_part and time_part else None


def _extract_boolean(raw: str) -> bool | None:
    normalized = raw.strip().lower().rstrip(".!")
    if normalized in _CONSENT_YES:
        return True
    if normalized in _CONSENT_NO:
        return False
    return None


def _match_select_option(raw: str, options: list[dict]) -> str | None:
    normalized = raw.strip().lower()
    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(options):
            return str(options[index].get("value"))
    for option in options:
        label = str(option.get("label", "")).strip().lower()
        value = str(option.get("value", "")).strip().lower()
        if normalized in (label, value):
            return str(option.get("value"))
    return None


def _match_multi_select(raw: str, options: list[dict]) -> list[str] | None:
    parts = re.split(r",| and |;", raw)
    matched: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        value = _match_select_option(part, options)
        if value is None:
            # Any unmatched part invalidates the whole extraction — a
            # partial multi-select capture would be a silent data-loss bug.
            return None
        if value not in matched:
            matched.append(value)
    return matched or None


def extract_value_for_field(
    field_summary: QualificationFieldSummary, raw_message: str
) -> tuple[object | None, str | None]:
    """Returns (value, rejection_reason). At most one is non-None. Both
    None means "no attempt" (e.g. consent wasn't explicit) rather than a
    rejection worth surfacing to the user."""
    field_type = field_summary.type
    text = raw_message.strip()
    if not text:
        return None, None

    if field_type == "email":
        email_value = _normalize_email(text)
        return (email_value, None) if email_value else (None, "I couldn't find a valid email address in that.")

    if field_type == "phone":
        phone_value = _normalize_phone(text)
        return (phone_value, None) if phone_value else (None, "I couldn't find a valid phone number in that.")

    if field_type == "number":
        number_value = _extract_number(text)
        return (number_value, None) if number_value is not None else (None, "I couldn't find a number in that.")

    if field_type == "currency":
        currency_value = _extract_currency(text)
        return (currency_value, None) if currency_value is not None else (None, "I couldn't find an amount in that.")

    if field_type == "date":
        date_value = _extract_date(text)
        return (date_value, None) if date_value else (None, "I couldn't find a valid date in that (try YYYY-MM-DD).")

    if field_type == "time":
        time_value = _extract_time(text)
        return (time_value, None) if time_value else (None, "I couldn't find a valid time in that.")

    if field_type == "datetime":
        datetime_value = _extract_datetime(text)
        return (datetime_value, None) if datetime_value else (None, "I need both a date and a time.")

    if field_type == "boolean":
        bool_value = _extract_boolean(text)
        return (bool_value, None) if bool_value is not None else (None, None)

    if field_type == "single_select":
        select_value = _match_select_option(text, field_summary.options or [])
        return (select_value, None) if select_value else (None, "That doesn't match one of the available options.")

    if field_type == "multi_select":
        multi_select_values = _match_multi_select(text, field_summary.options or [])
        if multi_select_values:
            return multi_select_values, None
        return None, "That doesn't match the available options."

    if field_type == "short_text":
        try:
            reject_html(text)
        except ValueError:
            return None, "That contains characters I can't accept here."
        if len(text) > MAX_SHORT_TEXT_ANSWER:
            return None, f"That's too long — please keep it under {MAX_SHORT_TEXT_ANSWER} characters."
        return text, None

    if field_type == "long_text":
        # "Where safely attributable" — require a minimum length so a
        # short unrelated aside isn't mistaken for a deliberate answer.
        if len(text) < MIN_LONG_TEXT_ANSWER:
            return None, None
        try:
            reject_html(text)
        except ValueError:
            return None, "That contains characters I can't accept here."
        if len(text) > MAX_LONG_TEXT_ANSWER:
            return None, f"That's too long — please keep it under {MAX_LONG_TEXT_ANSWER} characters."
        return text, None

    return None, None


@dataclass
class ExtractionOutcome:
    captured: dict[str, object] = field(default_factory=dict)
    corrected: dict[str, object] = field(default_factory=dict)
    rejected: list[QualificationRejection] = field(default_factory=list)


def process_message(
    *,
    all_fields: list[QualificationFieldSummary],
    pending_field: QualificationFieldSummary | None,
    collected_data: dict,
    raw_message: str,
) -> ExtractionOutcome:
    outcome = ExtractionOutcome()
    lowered = raw_message.strip().lower()

    if any(trigger in lowered for trigger in _CORRECTION_TRIGGERS):
        already_captured = [f for f in all_fields if f.key in collected_data]
        matched_field: QualificationFieldSummary | None = None
        matched_value: object | None = None
        ambiguous = False
        for candidate in already_captured:
            value, _ = extract_value_for_field(candidate, raw_message)
            if value is not None:
                if matched_field is not None:
                    ambiguous = True
                    break
                matched_field, matched_value = candidate, value
        if matched_field is not None and not ambiguous:
            outcome.corrected[matched_field.key] = matched_value
            return outcome

    if pending_field is not None:
        value, rejection_reason = extract_value_for_field(pending_field, raw_message)
        if value is not None:
            outcome.captured[pending_field.key] = value
        elif rejection_reason is not None:
            outcome.rejected.append(
                QualificationRejection(
                    field_key=pending_field.key, field_label=pending_field.label, reason=rejection_reason
                )
            )

    return outcome
