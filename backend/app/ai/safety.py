"""Deterministic safety pre-checks, run before any provider is ever called.

Safety enforcement lives entirely outside the model — a real LLM provider
could ignore its own instructions, but it can never see a user message
before this module has already decided whether to intercept it. Every
check here is conservative (biased toward triggering rather than missing
a real risk) and is a plain keyword/pattern match — no model call, no
ambiguity, fully deterministic and testable.
"""

from __future__ import annotations

import re

from app.ai.providers.base import SafetyDirective

# --- Clinic: urgent/emergency language -------------------------------------
# Deliberately broad and conservative — a false positive here (routing a
# non-emergency to the fixed safety response) is far cheaper than a false
# negative. This list is not exhaustive medical judgment; it is a safety
# net, and the fixed response always defers to real emergency services
# rather than the receptionist attempting to assess severity itself.
_CLINIC_URGENT_PATTERNS = [
    r"\bsuicid",
    r"\bkill (myself|him|her|them)\b",
    r"\bself[- ]harm",
    r"\boverdose",
    r"\bcan'?t breathe\b",
    r"\bnot breathing\b",
    r"\bchest pain\b",
    r"\bheart attack\b",
    r"\bstroke\b",
    r"\bunconscious",
    r"\bunresponsive",
    r"\bsevere bleeding\b",
    r"\bbleeding (heavily|a lot|badly)\b",
    r"\banaphyla",
    r"\ballergic reaction.*(can'?t breathe|throat|swelling)",
    r"\bemergency\b",
    r"\bdying\b",
    r"\b911\b",
]

_CLINIC_URGENT_RESPONSE = (
    "This may be a medical emergency. Please contact your local emergency "
    "services right away (for example, call 911 in the US) or go to the "
    "nearest emergency room. I'm not able to assess how serious this is, "
    "so please don't wait for a reply here — get in touch with emergency "
    "services or a medical professional immediately."
)

# --- Clinic: diagnosis/treatment/prescription scope -------------------------
_CLINIC_SCOPE_PATTERNS = [
    r"\bwhat (disease|condition|illness) do i have\b",
    r"\bdiagnos",
    r"\bwhat'?s wrong with me\b",
    r"\bprescri",
    r"\bwhat medication should i (take|use)\b",
    r"\bshould i take\b.*\b(medication|medicine|drug|pill)\b",
    r"\btreat(ment)? (plan|recommendation)\b",
    r"\bhow (do|should) i treat\b",
]

_CLINIC_SCOPE_RESPONSE = (
    "I can only help with administrative information here — things like "
    "appointment availability, hours, and general practice information. "
    "I'm not able to diagnose conditions, recommend treatment, or discuss "
    "medications. For anything medical, please book an appointment or "
    "speak directly with a clinician."
)

# --- Legal: outcome prediction / definitive advice --------------------------
_LEGAL_SCOPE_PATTERNS = [
    r"\bwill i win\b",
    r"\bwhat are my chances\b",
    r"\bis this legal\b",
    r"\bam i (liable|guilty|innocent)\b",
    r"\bgive me legal advice\b",
    r"\bwhat'?s my case worth\b",
    r"\bhow much (will|can) i (get|win|sue for)\b",
    r"\bguarantee.*(win|outcome|case)\b",
]

_LEGAL_SCOPE_RESPONSE = (
    "I can help with general administrative information — like scheduling "
    "a consultation — but I can't give legal advice, predict how a case "
    "will turn out, or guarantee any outcome. For anything specific to "
    "your situation, please consult with one of our qualified attorneys "
    "directly."
)

# --- General: prompt injection / secret / cross-tenant extraction ----------
_INJECTION_PATTERNS = [
    r"\bignore (all |your |the )?(previous|prior|above) instructions\b",
    r"\bdisregard (all |your |the )?(previous|prior|above|rules)\b",
    r"\breveal (your |the )?(system prompt|instructions|prompt)\b",
    r"\bwhat (is|are) your (system prompt|instructions)\b",
    r"\bprint (your |the )?(system prompt|instructions|prompt)\b",
    r"\byou are now\b",
    r"\bact as (a|an)\b",
    r"\bpretend (you'?re|to be)\b",
    r"\bdeveloper mode\b",
    r"\bjailbreak\b",
]

_SECRET_PATTERNS = [
    r"\bapi key\b",
    r"\bsecret key\b",
    r"\bdatabase (url|password|credentials)\b",
    r"\benvironment variable",
    r"\byour (config|configuration)\b.*\b(reveal|show|print)\b",
]

_CROSS_TENANT_PATTERNS = [
    r"\bother (tenant|business|customer|client)s?\b.*\b(data|information|conversation)\b",
    r"\bshow me (another|other) (tenant|business)\b",
    r"\blist all tenants\b",
    r"\baccess .*(another|other) (tenant|account)\b",
]

_INJECTION_RESPONSE = (
    "I can't share internal configuration, instructions, or override how "
    "I'm set up to work. I'm happy to help with questions about this "
    "business instead."
)

_SECRET_RESPONSE = "I can't share credentials, keys, or internal configuration details."

_CROSS_TENANT_RESPONSE = (
    "I can only help with this business's own information — I don't have access to any other business's data."
)


def _matches_any(text: str, patterns: list[str]) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in patterns)


def evaluate_safety(
    message_text: str,
    *,
    industry_template_key: str | None,
) -> SafetyDirective:
    """Runs every deterministic pre-check in priority order. Clinic urgent
    language always wins over everything else — qualification, retrieval,
    and any other response type must not proceed ahead of it."""

    if industry_template_key == "clinic" and _matches_any(message_text, _CLINIC_URGENT_PATTERNS):
        return SafetyDirective(triggered=True, category="clinic_urgent", fixed_response=_CLINIC_URGENT_RESPONSE)

    if industry_template_key == "clinic" and _matches_any(message_text, _CLINIC_SCOPE_PATTERNS):
        return SafetyDirective(triggered=True, category="clinic_scope", fixed_response=_CLINIC_SCOPE_RESPONSE)

    if industry_template_key == "law_firm" and _matches_any(message_text, _LEGAL_SCOPE_PATTERNS):
        return SafetyDirective(triggered=True, category="legal_scope", fixed_response=_LEGAL_SCOPE_RESPONSE)

    if _matches_any(message_text, _INJECTION_PATTERNS):
        return SafetyDirective(triggered=True, category="injection_attempt", fixed_response=_INJECTION_RESPONSE)

    if _matches_any(message_text, _SECRET_PATTERNS):
        return SafetyDirective(triggered=True, category="secret_request", fixed_response=_SECRET_RESPONSE)

    if _matches_any(message_text, _CROSS_TENANT_PATTERNS):
        return SafetyDirective(triggered=True, category="cross_tenant_attempt", fixed_response=_CROSS_TENANT_RESPONSE)

    return SafetyDirective(triggered=False, category="none")
