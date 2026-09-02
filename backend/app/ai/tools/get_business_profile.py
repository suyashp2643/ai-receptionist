from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.ai.tools.base import BaseTool, ToolContext
from app.repositories.business_profile import BusinessProfileRepository


class GetBusinessProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GetBusinessProfileTool(BaseTool):
    name = "get_business_profile"
    description = "Get this business's public profile (name, description, public contact details)."
    input_model = GetBusinessProfileInput

    def run(self, *, db: Session, context: ToolContext, tool_input: GetBusinessProfileInput) -> dict:  # type: ignore[override]
        profile = BusinessProfileRepository(db).get_by_tenant_id(context.tenant_id)
        if profile is None:
            return {}
        return {
            "business_name": profile.business_name,
            "short_description": profile.short_description,
            "website_url": profile.website_url,
            "public_email": profile.public_email,
            "public_phone": profile.public_phone,
        }
