"""A disabled placeholder adapter.

No `openai` SDK dependency is added, and no network code exists in this
module at all — every method raises `ProviderDisabledError` immediately,
regardless of whether an API key is configured. This is intentional: Phase
4 ships the interface and the configuration surface (`OPENAI_API_KEY` in
`.env.example`) so a real integration can be wired in later without
touching orchestration code, but no real integration is implemented yet.

To make this provider operational in a future phase: implement `generate`
and `stream` using the official `openai` SDK, add it to
`requirements.txt`, and remove the unconditional `ProviderDisabledError`
below — orchestration code needs no changes, since it only depends on the
`AIProvider` interface.
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

OPENAI_PROVIDER_NAME = "openai"

_DISABLED_MESSAGE = (
    "The OpenAI provider is not implemented in Phase 4 — only the mock "
    "provider is functional. Set AI_PROVIDER=mock to use it."
)


class OpenAIProvider(AIProvider):
    name = OPENAI_PROVIDER_NAME

    def __init__(self, api_key: str | None = None):
        # Stored only for future use — never logged, never sent anywhere,
        # and irrelevant to every method below since they all refuse to run.
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
