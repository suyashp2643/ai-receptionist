import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.allowlists import SUPPORTED_LANGUAGE_CODES
from app.core.text_safety import (
    MAX_MEDIUM_TEXT,
    MAX_SHORT_TEXT,
    validate_optional_phone,
    validate_optional_plain_text,
    validate_plain_text,
)
from app.core.timezones import VALID_TIMEZONES
from app.models.enums import OnboardingStatus


def _validate_language_code(value: str) -> str:
    if value not in SUPPORTED_LANGUAGE_CODES:
        raise ValueError(f"Unsupported language code: {value!r}")
    return value


class BusinessProfileUpdate(BaseModel):
    business_name: str | None = Field(default=None, max_length=MAX_SHORT_TEXT)
    short_description: str | None = Field(default=None, max_length=MAX_MEDIUM_TEXT)
    website_url: str | None = Field(default=None, max_length=500)
    public_email: EmailStr | None = None
    public_phone: str | None = None
    timezone: str | None = None
    default_language: str | None = None
    supported_languages: list[str] | None = None

    @field_validator("business_name")
    @classmethod
    def _business_name(cls, v: str | None) -> str | None:
        return validate_optional_plain_text(v, max_length=MAX_SHORT_TEXT)

    @field_validator("short_description")
    @classmethod
    def _short_description(cls, v: str | None) -> str | None:
        return validate_optional_plain_text(v, max_length=MAX_MEDIUM_TEXT)

    @field_validator("website_url")
    @classmethod
    def _website_url(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("website_url must start with http:// or https://")
        if len(v) > 500:
            raise ValueError("website_url is too long.")
        return v

    @field_validator("public_phone")
    @classmethod
    def _public_phone(cls, v: str | None) -> str | None:
        return validate_optional_phone(v)

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_TIMEZONES:
            raise ValueError(f"Unknown IANA timezone: {v!r}")
        return v

    @field_validator("default_language")
    @classmethod
    def _default_language(cls, v: str | None) -> str | None:
        return _validate_language_code(v) if v is not None else v

    @field_validator("supported_languages")
    @classmethod
    def _supported_languages(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        if len(v) > 20:
            raise ValueError("Too many supported languages.")
        return [_validate_language_code(code) for code in v]

    @model_validator(mode="after")
    def _default_language_must_be_supported(self) -> "BusinessProfileUpdate":
        if (
            self.default_language is not None
            and self.supported_languages is not None
            and self.default_language not in self.supported_languages
        ):
            raise ValueError("default_language must be included in supported_languages.")
        return self


class BusinessProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tenant_id: uuid.UUID
    business_name: str | None
    short_description: str | None
    website_url: str | None
    public_email: str | None
    public_phone: str | None
    industry_template_id: uuid.UUID | None
    timezone: str
    default_language: str
    supported_languages: list
    onboarding_status: OnboardingStatus
    onboarding_completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SelectIndustryRequest(BaseModel):
    template_key: str = Field(min_length=1, max_length=64)

    @field_validator("template_key")
    @classmethod
    def _key(cls, v: str) -> str:
        return validate_plain_text(v, max_length=64)


class OnboardingStepStatus(BaseModel):
    business_profile: bool
    industry_selected: bool
    receptionist: bool
    locations: bool
    services: bool
    knowledge: bool
    qualification: bool
    actions: bool


class OnboardingRequirement(BaseModel):
    """One thing blocking completion (or, if onboarding is already
    `completed`, one thing that has since regressed below the minimum bar —
    see docs/PROGRESS.md for why regression never un-completes onboarding).

    `step` names an onboarding route segment (e.g. "receptionist") so the
    frontend can link the user directly to the page that fixes it.
    """

    code: str
    message: str
    step: str


class OnboardingState(BaseModel):
    status: OnboardingStatus
    completed_at: datetime | None
    ready_to_complete: bool
    steps: OnboardingStepStatus
    incomplete_requirements: list[OnboardingRequirement]
    business_profile: BusinessProfileRead | None
