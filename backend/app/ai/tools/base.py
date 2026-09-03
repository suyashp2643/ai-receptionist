"""The typed, server-defined controlled-tool registry.

Every tool receives a `ToolContext` built entirely from the authenticated
request's already-resolved tenant/receptionist — never from provider- or
client-supplied arguments. No tool's Pydantic input model has a
`tenant_id` (or any tenant-selecting) field, so there is nothing for a
provider to override even if it tried; `execute_tool` below also never
merges provider-supplied arguments into `ToolContext`.
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.ai.providers.base import ToolDefinition, ToolExecutionResult

logger = logging.getLogger("app.ai.tools")

# Bounds applied uniformly to every tool's output, regardless of what the
# tool itself already trims — defense in depth against a future tool
# forgetting to bound its own result.
MAX_TOOL_OUTPUT_ITEMS = 20
MAX_TOOL_OUTPUT_STRING_CHARS = 2000


@dataclass(frozen=True)
class ToolContext:
    tenant_id: uuid.UUID
    receptionist_id: uuid.UUID


class BaseTool(ABC):
    name: str
    description: str
    input_model: type[BaseModel]

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters_schema=self.input_model.model_json_schema(),
        )

    @abstractmethod
    def run(self, *, db: Session, context: ToolContext, tool_input: BaseModel) -> dict:
        """Returns a plain, JSON-serializable dict. Should not raise for
        expected empty-result cases (e.g. no services configured) — only
        for genuine failures, which `execute_tool` converts to a safe
        error result rather than propagating."""


def _bound_output(value: object, *, depth: int = 0) -> object:
    """Recursively bounds list length and string length in a tool's raw
    output — a defensive backstop, not the primary bounding mechanism
    (each tool already caps its own result sizes).

    depth > 4 (Phase 7 bug, found via live testing of the public demos):
    get_business_hours' legitimate output is
    {"days": [ {"intervals": [ {"start": "08:00", ...} ] } ]} — dict(0) ->
    list(1) -> dict(2) -> list(3) -> dict(4) -> the "08:00" string itself is
    visited at depth=5, one level past a cutoff of >4, silently replacing
    every real start/end time with None and producing a "None-None" hours
    response with no error anywhere in the pipeline (the tool call itself
    reports status "ok"). 8 keeps meaningful headroom above any
    currently-shipped tool's real nesting while still bounding a
    pathologically deep structure."""
    if depth > 8:
        return None
    if isinstance(value, str):
        return value if len(value) <= MAX_TOOL_OUTPUT_STRING_CHARS else value[:MAX_TOOL_OUTPUT_STRING_CHARS]
    if isinstance(value, list):
        return [_bound_output(item, depth=depth + 1) for item in value[:MAX_TOOL_OUTPUT_ITEMS]]
    if isinstance(value, dict):
        return {str(k): _bound_output(v, depth=depth + 1) for k, v in value.items()}
    return value


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def definitions(self, *, allowed_names: set[str]) -> list[ToolDefinition]:
        return [tool.definition() for name, tool in self._tools.items() if name in allowed_names]

    def names(self) -> set[str]:
        return set(self._tools.keys())


def execute_tool(
    registry: ToolRegistry,
    *,
    call_id: str,
    name: str,
    arguments: dict,
    allowed_names: set[str],
    db: Session,
    context: ToolContext,
) -> ToolExecutionResult:
    if name not in allowed_names:
        logger.info("tool_call_rejected", extra={"tool_name": name, "reason": "not_allowed"})
        return ToolExecutionResult(tool_name=name, call_id=call_id, status="error", error_message="Tool not available.")

    tool = registry.get(name)
    if tool is None:
        logger.info("tool_call_rejected", extra={"tool_name": name, "reason": "unknown"})
        return ToolExecutionResult(tool_name=name, call_id=call_id, status="error", error_message="Unknown tool.")

    try:
        validated_input = tool.input_model.model_validate(arguments)
    except ValidationError:
        logger.info("tool_call_rejected", extra={"tool_name": name, "reason": "invalid_input"})
        return ToolExecutionResult(tool_name=name, call_id=call_id, status="error", error_message="Invalid tool input.")

    try:
        output = tool.run(db=db, context=context, tool_input=validated_input)
    except Exception:
        logger.exception("tool_execution_failed", extra={"tool_name": name})
        return ToolExecutionResult(
            tool_name=name, call_id=call_id, status="error", error_message="Tool execution failed."
        )

    bounded_output = _bound_output(output)
    if not isinstance(bounded_output, dict):
        bounded_output = {}
    logger.info("tool_call_executed", extra={"tool_name": name, "status": "ok"})
    return ToolExecutionResult(tool_name=name, call_id=call_id, status="ok", output=bounded_output)
