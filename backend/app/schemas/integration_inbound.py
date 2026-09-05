"""The inbound integration API's request/response contract. Deliberately
tiny and closed: `InboundEventType` is the entire allow-list of event
types this app will ever accept from an external caller — an unknown
value is rejected by Pydantic/FastAPI itself (422) before any service code
runs, not validated ad hoc. `InboundEventData` is similarly closed
(`extra="forbid"`): there is no field that names a column, a SQL
expression, or anything else that could be interpreted as code — see
app/api/v1/integrations_inbound.py's own docstring for why this API can
never perform an arbitrary mutation.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class InboundEventType(str, Enum):
    LEAD_STATUS_UPDATED = "lead.status_updated"
    LEAD_NOTE = "lead.note"


class InboundEventData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_reference: str = Field(max_length=300)
    note: str = Field(max_length=2000)


class InboundEventSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_event_id: str = Field(min_length=1, max_length=300)
    event_type: InboundEventType
    event_version: int = Field(ge=1, le=1)
    data: InboundEventData


class InboundEventSubmitResponse(BaseModel):
    status: str  # "processed" | "duplicate"
    external_event_id: str
