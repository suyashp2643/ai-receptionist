from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.ai.tools.base import BaseTool, ToolContext
from app.repositories.business_location import BusinessLocationRepository

_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class GetBusinessHoursInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GetBusinessHoursTool(BaseTool):
    name = "get_business_hours"
    description = "Get this business's working hours for its primary (or first active) location."
    input_model = GetBusinessHoursInput

    def run(self, *, db: Session, context: ToolContext, tool_input: GetBusinessHoursInput) -> dict:  # type: ignore[override]
        repo = BusinessLocationRepository(db, context.tenant_id)
        location = repo.get_primary()
        if location is None or not location.is_active:
            active_locations = [loc for loc in repo.list_ordered() if loc.is_active]
            location = active_locations[0] if active_locations else None

        if location is None:
            return {"days": [], "location_name": None}

        days = location.working_hours.get("days", []) if isinstance(location.working_hours, dict) else []
        enriched = []
        for day in days[:7]:
            day_of_week = day.get("day_of_week")
            if not isinstance(day_of_week, int) or not (0 <= day_of_week <= 6):
                continue
            enriched.append(
                {
                    "day_of_week": day_of_week,
                    "day_name": _DAY_NAMES[day_of_week],
                    "closed": bool(day.get("closed", True)),
                    "intervals": [
                        {"start": interval.get("start"), "end": interval.get("end")}
                        for interval in day.get("intervals", [])[:5]
                    ],
                }
            )
        return {"days": enriched, "location_name": location.name}
