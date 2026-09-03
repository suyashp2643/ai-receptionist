from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.text_safety import (
    MAX_LONG_TEXT,
    MAX_MEDIUM_TEXT,
    MAX_SHORT_TEXT,
    validate_optional_plain_text,
    validate_plain_text,
)

# Deliberately generous but bounded — a lead is a short qualification form,
# never a knowledge document.
_MAX_MESSAGE = MAX_LONG_TEXT


class PublicLeadCreateRequest(BaseModel):
    """The public contact/demo-request form's submission contract. Every
    field is server-validated and length-capped regardless of what the
    client sends — see app/core/text_safety.py's plain-text policy (any
    `<`/`>` is rejected outright rather than attempting HTML sanitization).

    `hp_field` is a honeypot: real visitors never see or fill this input
    (hidden via CSS on the public form), so a non-empty value here means an
    automated submission. The service layer accepts the request with a
    generic success response either way — never revealing that spam
    detection exists — but does not persist a honeypot-triggered
    submission."""

    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(max_length=MAX_SHORT_TEXT)
    work_email: EmailStr
    company: str = Field(max_length=MAX_SHORT_TEXT)
    website: str | None = Field(default=None, max_length=500)
    country: str = Field(max_length=MAX_SHORT_TEXT)
    industry: str = Field(max_length=MAX_SHORT_TEXT)
    company_size: str = Field(max_length=MAX_SHORT_TEXT)
    estimated_monthly_volume: str = Field(max_length=MAX_SHORT_TEXT)
    primary_use_case: str = Field(max_length=MAX_MEDIUM_TEXT)
    message: str = Field(max_length=_MAX_MESSAGE)
    contact_consent: bool
    marketing_consent: bool = False
    hp_field: str = Field(default="", max_length=200)

    @field_validator("full_name", "company", "country", "industry", "company_size", "estimated_monthly_volume")
    @classmethod
    def _short_plain_text(cls, v: str) -> str:
        return validate_plain_text(v, max_length=MAX_SHORT_TEXT)

    @field_validator("primary_use_case")
    @classmethod
    def _use_case(cls, v: str) -> str:
        return validate_plain_text(v, max_length=MAX_MEDIUM_TEXT)

    @field_validator("message")
    @classmethod
    def _message(cls, v: str) -> str:
        return validate_plain_text(v, max_length=_MAX_MESSAGE)

    @field_validator("website")
    @classmethod
    def _website(cls, v: str | None) -> str | None:
        v = validate_optional_plain_text(v, max_length=500)
        if v is None:
            return None
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("website must start with http:// or https://")
        return v

    @field_validator("contact_consent")
    @classmethod
    def _contact_consent_required(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Contact consent is required to submit this form.")
        return v


class PublicLeadSubmitResponse(BaseModel):
    """Deliberately generic — identical whether the submission was stored
    or silently dropped as a honeypot hit, so a caller can never use the
    response to detect spam filtering."""

    received: bool = True
