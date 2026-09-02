import socket

import pytest
from app.ai.providers.anthropic_provider import AnthropicProvider
from app.ai.providers.base import (
    ConversationContext,
    GenerateRequest,
    ProviderConfigurationError,
    ProviderDisabledError,
    ProviderFinishReason,
    ProviderMessage,
    QualificationState,
    SafetyDirective,
)
from app.ai.providers.factory import get_provider
from app.ai.providers.mock import MockProvider
from app.ai.providers.openai_provider import OpenAIProvider
from app.config import Settings


def _context(**overrides) -> ConversationContext:
    defaults = {
        "receptionist_name": "Ada",
        "business_name": "Acme Realty",
        "qualification": QualificationState(),
        "safety": SafetyDirective(),
    }
    defaults.update(overrides)
    return ConversationContext(**defaults)


def _request(text: str, **context_overrides) -> GenerateRequest:
    return GenerateRequest(messages=[ProviderMessage(role="user", content=text)], context=_context(**context_overrides))


class TestMockProviderDeterminism:
    def test_generate_is_deterministic_for_identical_input(self):
        provider = MockProvider()
        request = _request("What are your hours?")
        first = provider.generate(request)
        second = provider.generate(request)
        assert first.content == second.content
        assert first.finish_reason == second.finish_reason

    def test_streaming_chunks_reconstruct_the_complete_response(self):
        provider = MockProvider()
        request = _request("Tell me about your business.")
        full = provider.generate(request).content
        streamed = "".join(chunk.delta for chunk in provider.stream(request))
        assert streamed == full

    def test_stream_emits_exactly_one_terminal_finish_reason(self):
        provider = MockProvider()
        chunks = list(provider.stream(_request("hello")))
        terminal = [c for c in chunks if c.finish_reason is not None]
        assert len(terminal) == 1
        assert terminal[0] is chunks[-1]

    def test_never_claims_to_be_a_live_external_model(self):
        provider = MockProvider()
        result = provider.generate(_request("who are you? are you chatgpt or a real ai?"))
        lowered = result.content.lower()
        assert "chatgpt" not in lowered
        assert "gpt-4" not in lowered
        assert "claude" not in lowered

    def test_safety_triggered_short_circuits_to_the_fixed_response(self):
        provider = MockProvider()
        directive = SafetyDirective(triggered=True, category="clinic_urgent", fixed_response="Call emergency services.")
        request = _request("chest pain", safety=directive)
        result = provider.generate(request)
        assert result.content == "Call emergency services."
        assert result.finish_reason == ProviderFinishReason.STOP

    def test_summarize_never_invents_captured_requirements(self):
        provider = MockProvider()
        qualification = QualificationState(collected_data={"email": "a@example.com"}, qualification_complete=True)
        context = _context(qualification=qualification)
        result = provider.summarize(context)
        assert result.captured_requirements == {"email": "a@example.com"}

    def test_capabilities_report_mock_as_enabled_and_streaming(self):
        capabilities = MockProvider().capabilities()
        assert capabilities.name == "mock"
        assert capabilities.enabled is True
        assert capabilities.streaming is True


class TestNoExternalNetworkAccess:
    def test_mock_provider_module_imports_no_networking_library(self):
        import app.ai.providers.mock as mock_module

        source = open(mock_module.__file__, encoding="utf-8").read()
        for forbidden in ("import requests", "import httpx", "import urllib", "import socket", "openai", "anthropic"):
            assert forbidden not in source

    def test_mock_provider_makes_no_socket_connections(self, monkeypatch):
        def _blocked(*args, **kwargs):
            raise AssertionError("MockProvider attempted a real network connection")

        monkeypatch.setattr(socket.socket, "connect", _blocked)
        provider = MockProvider()
        request = _request("What services do you offer?")
        provider.generate(request)
        list(provider.stream(request))
        provider.summarize(_context())


class TestDisabledProviders:
    @pytest.mark.parametrize("provider_cls", [OpenAIProvider, AnthropicProvider])
    def test_generate_raises_disabled_error_even_with_a_key(self, provider_cls):
        provider = provider_cls(api_key="sk-not-a-real-key")
        with pytest.raises(ProviderDisabledError):
            provider.generate(_request("hello"))

    @pytest.mark.parametrize("provider_cls", [OpenAIProvider, AnthropicProvider])
    def test_stream_raises_disabled_error(self, provider_cls):
        provider = provider_cls(api_key="sk-not-a-real-key")
        with pytest.raises(ProviderDisabledError):
            list(provider.stream(_request("hello")))

    @pytest.mark.parametrize("provider_cls", [OpenAIProvider, AnthropicProvider])
    def test_capabilities_report_disabled(self, provider_cls):
        capabilities = provider_cls().capabilities()
        assert capabilities.enabled is False


class TestProviderFactory:
    def test_mock_is_the_default(self):
        provider = get_provider(Settings(ai_provider="mock"))
        assert isinstance(provider, MockProvider)

    def test_unknown_provider_name_fails_at_resolution(self):
        with pytest.raises(ProviderConfigurationError):
            get_provider(Settings(ai_provider="some_made_up_provider"))

    def test_openai_without_a_key_fails_safely(self):
        with pytest.raises(ProviderConfigurationError):
            get_provider(Settings(ai_provider="openai", openai_api_key=None))

    def test_anthropic_without_a_key_fails_safely(self):
        with pytest.raises(ProviderConfigurationError):
            get_provider(Settings(ai_provider="anthropic", anthropic_api_key=None))

    def test_openai_with_a_key_resolves_but_remains_a_disabled_adapter(self):
        provider = get_provider(Settings(ai_provider="openai", openai_api_key="sk-test"))
        assert isinstance(provider, OpenAIProvider)
        with pytest.raises(ProviderDisabledError):
            provider.generate(_request("hello"))


class TestNoProviderSpecificLeakage:
    def test_generate_request_and_result_types_are_shared_across_providers(self):
        """The same GenerateRequest/GenerateResult/ConversationContext types
        are constructed identically regardless of which provider class is
        used — nothing provider-specific is required to build one."""
        request = _request("hello")
        for provider in (MockProvider(), OpenAIProvider(), AnthropicProvider()):
            assert provider.capabilities().name in {"mock", "openai", "anthropic"}
        # A mock-produced result uses only contract types.
        result = MockProvider().generate(request)
        assert type(result).__module__ == "app.ai.providers.base"
