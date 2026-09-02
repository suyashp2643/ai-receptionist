"""Provider resolution from validated environment configuration.

Never silently falls back to another provider — an unknown name or a
selected-but-unconfigured provider fails loudly here, at resolution time.
"""

from app.ai.providers.anthropic_provider import AnthropicProvider
from app.ai.providers.base import AIProvider, ProviderConfigurationError
from app.ai.providers.mock import MockProvider
from app.ai.providers.openai_provider import OpenAIProvider
from app.config import Settings

_KNOWN_PROVIDERS = frozenset({"mock", "openai", "anthropic"})


def get_provider(settings: Settings) -> AIProvider:
    name = settings.ai_provider.strip().lower()

    if name not in _KNOWN_PROVIDERS:
        raise ProviderConfigurationError(
            f"Unknown AI_PROVIDER {settings.ai_provider!r}. Supported values: {sorted(_KNOWN_PROVIDERS)}."
        )

    if name == "mock":
        return MockProvider()

    if name == "openai":
        if not settings.openai_api_key:
            raise ProviderConfigurationError(
                "AI_PROVIDER=openai requires OPENAI_API_KEY to be set. Note that even with a key "
                "configured, the OpenAI provider is a disabled placeholder in Phase 4 — see "
                "app/ai/providers/openai_provider.py."
            )
        return OpenAIProvider(api_key=settings.openai_api_key)

    # name == "anthropic"
    if not settings.anthropic_api_key:
        raise ProviderConfigurationError(
            "AI_PROVIDER=anthropic requires ANTHROPIC_API_KEY to be set. Note that even with a key "
            "configured, the Anthropic provider is a disabled placeholder in Phase 4 — see "
            "app/ai/providers/anthropic_provider.py."
        )
    return AnthropicProvider(api_key=settings.anthropic_api_key)
