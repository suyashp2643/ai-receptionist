from pydantic import BaseModel


class TimezoneListResponse(BaseModel):
    timezones: list[str]
