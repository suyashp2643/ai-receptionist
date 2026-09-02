"""The single, module-level tool registry — the server-defined set of
tool names/schemas a provider can ever be offered. Gating on the tenant's
enabled actions and the current phase happens separately in
`app/ai/orchestrator.py` (via `allowed_names`), not here — this registry
only knows what tools *exist*, not what any given tenant is allowed to
use."""

from app.ai.tools.base import ToolRegistry
from app.ai.tools.get_business_hours import GetBusinessHoursTool
from app.ai.tools.get_business_profile import GetBusinessProfileTool
from app.ai.tools.list_services import ListServicesTool
from app.ai.tools.search_business_knowledge import SearchBusinessKnowledgeTool

TOOL_REGISTRY = ToolRegistry()
TOOL_REGISTRY.register(SearchBusinessKnowledgeTool())
TOOL_REGISTRY.register(ListServicesTool())
TOOL_REGISTRY.register(GetBusinessHoursTool())
TOOL_REGISTRY.register(GetBusinessProfileTool())

# Phase 4 exposes all four read-only tools when the workflow has
# `answer_questions` enabled — see orchestrator.py. There is no separate
# "Phase 4 subset" here because every registered tool is already
# Phase-4-appropriate (read-only); nothing write-capable is ever
# registered.
PHASE_4_TOOL_NAMES: frozenset[str] = frozenset(TOOL_REGISTRY.names())
