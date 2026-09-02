"""A disabled placeholder adapter — see openai_provider.py's module
docstring; the same reasoning applies here. No `anthropic` SDK dependency
is added, and no network code exists in this module at all.
"""

from __future__ import annotations

from collections.abc import Iterator

from app.ai.providers.base import (
    AIProvider,
    ConversationContext,
    GenerateRequest,
    GenerateResult,
    ProviderCapabilities,
    ProviderDisabledError,
    StreamChunk,
    SummaryResult,
)

ANTHROPIC_PROVIDER_NAME = "anthropic"

_DISABLED_MESSAGE = (
    "The Anthropic provider is not implemented in Phase 4 — only the mock "
    "provider is functional. Set AI_PROVIDER=mock to use it."
)


class AnthropicProvider(AIProvider):
    name = ANTHROPIC_PROVIDER_NAME

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(name=self.name, streaming=False, tool_calls=False, enabled=False)

    def generate(self, request: GenerateRequest) -> GenerateResult:
        raise ProviderDisabledError(_DISABLED_MESSAGE)

    def stream(self, request: GenerateRequest) -> Iterator[StreamChunk]:
        raise ProviderDisabledError(_DISABLED_MESSAGE)
        yield  # pragma: no cover - makes this a generator function; unreachable

    def summarize(self, context: ConversationContext) -> SummaryResult:
        raise ProviderDisabledError(_DISABLED_MESSAGE)
