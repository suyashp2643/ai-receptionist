import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.text_safety import (
    MAX_KNOWLEDGE_TEXT,
    MAX_SHORT_TEXT,
    reject_html,
    validate_plain_text,
)
from app.models.enums import ContentStatus, KnowledgeSourceType


class KnowledgeSourceCreate(BaseModel):
    type: KnowledgeSourceType = KnowledgeSourceType.MANUAL
    title: str = Field(min_length=1, max_length=MAX_SHORT_TEXT)

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        return validate_plain_text(v, max_length=MAX_SHORT_TEXT)


class KnowledgeSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    type: KnowledgeSourceType
    title: str
    status: ContentStatus
    created_at: datetime
    updated_at: datetime


class KnowledgeDocumentCreate(BaseModel):
    source_id: uuid.UUID
    title: str = Field(min_length=1, max_length=MAX_SHORT_TEXT)
    raw_text: str = Field(min_length=1, max_length=MAX_KNOWLEDGE_TEXT)

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        return validate_plain_text(v, max_length=MAX_SHORT_TEXT)

    @field_validator("raw_text")
    @classmethod
    def _raw_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("raw_text cannot be empty.")
        if len(v) > MAX_KNOWLEDGE_TEXT:
            raise ValueError(f"raw_text must be at most {MAX_KNOWLEDGE_TEXT} characters.")
        # Plain text only, same policy as everywhere else — knowledge text is
        # never rendered as HTML and must never be treated as executable.
        return reject_html(v)


class KnowledgeDocumentUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=MAX_SHORT_TEXT)
    status: ContentStatus | None = None


class KnowledgeDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    source_id: uuid.UUID
    title: str
    raw_text: str
    status: ContentStatus
    created_at: datetime
    updated_at: datetime


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)

    @field_validator("query")
    @classmethod
    def _query(cls, v: str) -> str:
        return validate_plain_text(v, max_length=500)


class KnowledgeSearchResultItem(BaseModel):
    document_id: uuid.UUID
    document_title: str
    chunk_id: uuid.UUID
    chunk_index: int
    content: str
    score: float


class KnowledgeSearchResponse(BaseModel):
    query: str
    results: list[KnowledgeSearchResultItem]
