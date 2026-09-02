from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.ai.tools.base import BaseTool, ToolContext
from app.repositories.service import ServiceRepository


class ListServicesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListServicesTool(BaseTool):
    name = "list_services"
    description = "List this business's active services."
    input_model = ListServicesInput

    def run(self, *, db: Session, context: ToolContext, tool_input: ListServicesInput) -> dict:  # type: ignore[override]
        services = [s for s in ServiceRepository(db, context.tenant_id).list_ordered() if s.is_active][:20]
        return {
            "services": [
                {
                    "name": s.name,
                    "description": s.description,
                    "category": s.category,
                    "price_note": s.price_note,
                    "currency": s.currency,
                    "duration_minutes": s.duration_minutes,
                }
                for s in services
            ],
            "count": len(services),
        }
