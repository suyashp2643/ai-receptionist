from pydantic import BaseModel


class DatabaseHealth(BaseModel):
    status: str
    detail: str


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str
    database: DatabaseHealth
