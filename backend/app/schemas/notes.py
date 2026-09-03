import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NoteEntityType = Literal["conversation", "contact", "enquiry", "appointment_request", "human_handoff"]


class NoteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_type: NoteEntityType
    entity_id: uuid.UUID
    body: str = Field(min_length=1, max_length=4000)


class NoteUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=4000)


class NoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    author_user_id: uuid.UUID
    body: str
    created_at: datetime
    updated_at: datetime
