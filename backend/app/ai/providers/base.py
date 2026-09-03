"""The provider-independent AI contract.

Every type in this module is part of the *contract itself* — shared by
every provider implementation equally (mock, OpenAI, Anthropic) — so
nothing here counts as "provider-specific" leaking into orchestration.
`ConversationContext` in particular is the structured, already-assembled
view of a conversation turn (retrieved knowledge, qualification state,
safety directive, tool results) that any provider — mock today, a real LLM
later — receives as input. A real-LLM provider would render this into
natural-language system-prompt text; the mock provider consumes its
fields directly to compose a deterministic response.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Literal

from pydantic import BaseModel, Field


class ProviderFinishReason(str, enum.Enum):
    STOP = "stop"
    TOOL_CALLS = "tool_calls"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"
    ERROR = "error"


class ProviderMessage(BaseModel):
    """One turn of conversation history, in the shape any provider needs."""

    role: Literal["user", "assistant", "system", "tool"]
    content: str
    tool_call_id: str | None = None


class ToolDefinition(BaseModel):
    """How a controlled tool is advertised to a provider — never includes
    tenant/server-trusted fields; those are injected by the orchestrator at
    execution time, not supplied by (or to) the provider."""

    name: str
    description: str
    parameters_schema: dict = Field(default_factory=dict)


class ToolCallRequest(BaseModel):
    id: str
    name: str
    arguments: dict = Field(default_factory=dict)


class ProviderUsage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class ProviderCapabilities(BaseModel):
    name: str
    streaming: bool
    tool_calls: bool
    enabled: bool


class RetrievedSource(BaseModel):
    source_id: str
    source_type: Literal["faq", "knowledge_chunk", "service", "location", "business_profile"]
    title: str
    excerpt: str
    score: float
    metadata: dict = Field(default_factory=dict)


class QualificationFieldSummary(BaseModel):
    key: str
    label: str
    type: str
    options: list[dict] | None = None


class QualificationRejection(BaseModel):
    field_key: str
    field_label: str
    reason: str


class QualificationState(BaseModel):
    next_field: QualificationFieldSummary | None = None
    collected_data: dict = Field(default_factory=dict)
    missing_required_fields: list[str] = Field(default_factory=list)
    # Same fields as missing_required_fields, but full summaries (not just
    # keys) — used for the completion summary, where every unresolved
    # field needs a human-readable label, not only the single next one.
    missing_field_summaries: list[QualificationFieldSummary] = Field(default_factory=list)
    qualification_complete: bool = False
    # Full field summaries (not just keys) so a provider can phrase an
    # acknowledgment ("Got it — I've noted your email address.") without a
    # separate lookup against the workflow schema it never sees directly.
    just_captured: list[QualificationFieldSummary] = Field(default_factory=list)
    just_corrected: list[QualificationFieldSummary] = Field(default_factory=list)
    just_rejected: list[QualificationRejection] = Field(default_factory=list)


SafetyCategory = Literal[
    "clinic_urgent",
    "clinic_scope",
    "legal_scope",
    "injection_attempt",
    "secret_request",
    "cross_tenant_attempt",
    "none",
]


class SafetyDirective(BaseModel):
    triggered: bool = False
    category: SafetyCategory = "none"
    fixed_response: str | None = None


class ToolExecutionResult(BaseModel):
    tool_name: str
    call_id: str
    status: Literal["ok", "error"]
    output: dict = Field(default_factory=dict)
    error_message: str | None = None


class ConversationContext(BaseModel):
    receptionist_name: str
    business_name: str
    tone: str | None = None
    retrieved_sources: list[RetrievedSource] = Field(default_factory=list)
    qualification: QualificationState
    safety: SafetyDirective
    tool_results: list[ToolExecutionResult] = Field(default_factory=list)
    recommended_next_action: str | None = None
    turn_index: int = 0


class GenerateRequest(BaseModel):
    messages: list[ProviderMessage]
    tools: list[ToolDefinition] = Field(default_factory=list)
    context: ConversationContext
    max_tokens: int | None = None


class GenerateResult(BaseModel):
    content: str
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)
    finish_reason: ProviderFinishReason
    usage: ProviderUsage | None = None
    provider_message_id: str | None = None
    # Part of the provider-independent contract, not mock-specific: any
    # provider MAY set this to signal "I found nothing to answer this
    # with," for Phase 6's "unanswered / fallback responses" analytics
    # metric (app/services/analytics_service.py). Only MockProvider
    # currently sets it meaningfully (from its own known "found nothing"
    # response text) — a real LLM provider would need its own logic to set
    # this truthfully, and until one does, the metric is mock-only. See
    # docs/architecture.md's Phase 6 analytics section.
    is_fallback: bool = False


class StreamChunk(BaseModel):
    delta: str = ""
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)
    finish_reason: ProviderFinishReason | None = None
    usage: ProviderUsage | None = None
    provider_message_id: str | None = None
    is_fallback: bool = False


class ProviderError(Exception):
    """Base for every controlled provider error. Never carries raw
    provider SDK exceptions, API keys, or stack traces from a third-party
    client — routes catch this (or a subclass) and translate it to a safe
    bounded error code, never re-raising the underlying cause verbatim."""

    code: str = "provider_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ProviderConfigurationError(ProviderError):
    """An unknown provider name, or a selected provider missing required
    configuration (e.g. an API key) — raised at provider resolution, never
    silently falling back to another provider."""

    code = "provider_configuration_error"


class ProviderDisabledError(ProviderError):
    """Raised by every method of a provider adapter that exists only as an
    interface today (OpenAI, Anthropic) — regardless of whether credentials
    are configured. No network call is ever attempted by these adapters."""

    code = "provider_disabled"


class ProviderTimeoutError(ProviderError):
    code = "provider_timeout"


class ProviderRequestFailedError(ProviderError):
    code = "provider_request_failed"


class SummaryResult(BaseModel):
    summary: str
    captured_requirements: dict = Field(default_factory=dict)
    unresolved_questions: list[str] = Field(default_factory=list)
    recommended_next_action: str | None = None


class AIProvider(ABC):
    """Provider-independent interface. Orchestration code depends only on
    this ABC and the shared types above — never on a concrete provider's
    own request/response shapes."""

    name: str

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities: ...

    @abstractmethod
    def generate(self, request: GenerateRequest) -> GenerateResult:
        """A single, complete (non-streamed) response — used for the
        tool-call decision pass, where streaming would add nothing."""

    @abstractmethod
    def stream(self, request: GenerateRequest) -> Iterator[StreamChunk]:
        """The final, user-visible response, chunked for SSE delivery."""

    @abstractmethod
    def summarize(self, context: ConversationContext) -> SummaryResult:
        """Called once, on conversation completion — never mid-conversation."""
