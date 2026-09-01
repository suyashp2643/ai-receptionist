import zoneinfo

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from app.schemas.tenant import TenantMembershipSummary
from app.schemas.user import UserPublic

_VALID_TIMEZONES = zoneinfo.available_timezones()


class RegisterRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    workspace_name: str = Field(min_length=1, max_length=200)
    timezone: str = Field(default="UTC")

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        if v not in _VALID_TIMEZONES:
            raise ValueError(f"Unknown IANA timezone: {v!r}")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic
    memberships: list[TenantMembershipSummary]


class MeResponse(BaseModel):
    user: UserPublic
    memberships: list[TenantMembershipSummary]
