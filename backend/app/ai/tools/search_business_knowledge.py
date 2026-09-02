from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.ai.retrieval import RetrievalQuery, retrieve
from app.ai.tools.base import BaseTool, ToolContext


class SearchBusinessKnowledgeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=300)


class SearchBusinessKnowledgeTool(BaseTool):
    name = "search_business_knowledge"
    description = "Search this business's approved FAQs and knowledge base for information relevant to a question."
    input_model = SearchBusinessKnowledgeInput

    def run(self, *, db: Session, context: ToolContext, tool_input: SearchBusinessKnowledgeInput) -> dict:  # type: ignore[override]
        results = retrieve(db, tenant_id=context.tenant_id, query=RetrievalQuery(text=tool_input.query, limit=5))
        return {"results": [r.model_dump() for r in results], "count": len(results)}
