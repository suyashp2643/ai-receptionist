import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserPublic(BaseModel):
    """Never add password_hash here — this schema is what auth responses return."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    normalized_email: str
    display_name: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
