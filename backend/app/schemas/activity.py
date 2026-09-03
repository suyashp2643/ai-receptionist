import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ActivityEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action_type: str
    entity_type: str
    entity_id: uuid.UUID
    event_metadata: dict
    created_at: datetime


class ActivityListResponse(BaseModel):
    items: list[ActivityEventRead]
    total: int
    limit: int
    offset: int
