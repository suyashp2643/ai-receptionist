"""The default, fully-functional Phase 4 provider.

Deterministic and rule-based, not a real language model — see the module
docstring on why: it must be reproducible for automated tests and honest
about being a demonstration engine (never implying it is a live external
model), while still faithfully exercising the same orchestration shape a
real provider will use later (a tool-call decision pass, then a streamed
final-answer pass).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator

from app.ai.providers.base import (
    AIProvider,
    ConversationContext,
    GenerateRequest,
    GenerateResult,
    ProviderCapabilities,
    ProviderFinishReason,
    ProviderMessage,
    QualificationFieldSummary,
    QualificationState,
    RetrievedSource,
    StreamChunk,
    SummaryResult,
    ToolCallRequest,
    ToolExecutionResult,
)

MOCK_PROVIDER_NAME = "mock"

_HOURS_KEYWORDS = ("hour", "open", "close", "when are you")
_SERVICE_KEYWORDS = ("service", "offer", "price", "cost", "what do you do")
_QUESTION_STARTS = ("what", "how", "when", "where", "who", "why", "can", "do", "does", "is", "are", "could", "would")

_ACTION_PHRASES = {
    "request_callback": "Would you like us to arrange a callback?",
    "request_appointment": "Would you like to request an appointment?",
    "request_viewing": "Would you like to request a viewing?",
    "request_reservation": "Would you like to request a reservation?",
    "request_demo": "Would you like to request a demo?",
    "request_test_drive": "Would you like to request a test drive?",
    "request_service_visit": "Would you like to request a service visit?",
    "request_human_handoff": "Would you like to speak with a team member?",
    "capture_contact": "Could I get your contact details so our team can follow up?",
    "qualify_lead": "Let's go through a few quick questions.",
    "answer_questions": "Is there anything else I can help you with?",
}


def _deterministic_id(*parts: str) -> str:
    """A stable id derived from its inputs, not randomness — keeps the
    mock provider reproducible across runs for the same conversation
    state, which real UUIDs/timestamps would not be."""
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def _latest_user_message(messages: list[ProviderMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return ""


def _looks_like_question(text: str) -> bool:
    lowered = text.strip().lower()
    if lowered.endswith("?"):
        return True
    return any(lowered.startswith(word) for word in _QUESTION_STARTS)


def _decide_tool(text: str, available_tools: set[str], *, has_sources: bool) -> str | None:
    lowered = text.lower()
    if "get_business_hours" in available_tools and any(k in lowered for k in _HOURS_KEYWORDS):
        return "get_business_hours"
    if "list_services" in available_tools and any(k in lowered for k in _SERVICE_KEYWORDS):
        return "list_services"
    if "search_business_knowledge" in available_tools and not has_sources and _looks_like_question(text):
        return "search_business_knowledge"
    return None


def _tool_arguments(tool_name: str, latest_user_text: str) -> dict:
    if tool_name == "search_business_knowledge":
        return {"query": latest_user_text[:300]}
    return {}


def _format_hours(output: dict) -> str:
    days = output.get("days", [])
    open_days = [d for d in days if not d.get("closed")]
    if not open_days:
        return "I don't have business hours configured yet."
    parts = []
    for day in open_days:
        intervals = ", ".join(f"{i['start']}-{i['end']}" for i in day.get("intervals", []))
        parts.append(f"{day['day_name']}: {intervals}")
    return "Our hours are — " + "; ".join(parts) + "."


def _format_services(output: dict) -> str:
    services = output.get("services", [])
    if not services:
        return "I don't see any services listed yet."
    names = ", ".join(s["name"] for s in services[:5])
    return f"We offer: {names}."


def _format_knowledge_results(output: dict) -> str:
    results = output.get("results", [])
    if not results:
        return "I couldn't find anything about that in what's been shared with me."
    return str(results[0]["excerpt"])


def _format_profile(output: dict) -> str:
    name = output.get("business_name") or "our business"
    description = output.get("short_description")
    return f"{name}{' — ' + description if description else ''}."


_TOOL_FORMATTERS = {
    "get_business_hours": _format_hours,
    "list_services": _format_services,
    "search_business_knowledge": _format_knowledge_results,
    "get_business_profile": _format_profile,
}


def _answer_from_tools(tool_results: list[ToolExecutionResult]) -> str | None:
    pieces = []
    for result in tool_results:
        if result.status != "ok":
            continue
        formatter = _TOOL_FORMATTERS.get(result.tool_name)
        if formatter is not None:
            pieces.append(formatter(result.output))
    if pieces:
        return " ".join(pieces)
    if tool_results:
        return "I couldn't find that information in what's been shared with me."
    return None


def _answer_from_sources(sources: list[RetrievedSource]) -> str:
    return sources[0].excerpt


def _compose_answer(
    latest_user_text: str, sources: list[RetrievedSource], tool_results: list[ToolExecutionResult]
) -> str | None:
    from_tools = _answer_from_tools(tool_results)
    if from_tools is not None:
        return from_tools
    if sources:
        return _answer_from_sources(sources)
    if _looks_like_question(latest_user_text):
        return (
            "I don't have that information available right now, and I don't want to guess — "
            "let me know if there's something else I can help with, or a team member can follow up."
        )
    return None


def _acknowledgment(qualification: QualificationState) -> str | None:
    notes: list[str] = []
    if qualification.just_captured:
        labels = ", ".join(field.label for field in qualification.just_captured)
        notes.append(f"Got it — I've noted your {labels}.")
    if qualification.just_corrected:
        labels = ", ".join(field.label for field in qualification.just_corrected)
        notes.append(f"Updated your {labels}.")
    return " ".join(notes) if notes else None


def _rejection_note(qualification: QualificationState) -> str | None:
    if not qualification.just_rejected:
        return None
    parts = [f"That doesn't look like a valid {r.field_label} — {r.reason}" for r in qualification.just_rejected]
    return " ".join(parts)


def _question_for_field(field: QualificationFieldSummary) -> str:
    label = field.label.lower()
    # Some field labels are themselves phrased as questions (e.g. "What are
    # you looking to do?") — avoid a doubled "??" when that's the case.
    if label.endswith("?"):
        question = f"Could you tell me: {label}"
    else:
        question = f"Could you share your {label}?"
    if field.type in ("single_select", "multi_select") and field.options:
        option_labels = ", ".join(str(o.get("label", o.get("value", ""))) for o in field.options)
        question += f" (Options: {option_labels})"
    return question


def _next_action_offer(action: str) -> str:
    return _ACTION_PHRASES.get(action, "A team member can follow up with you next.")


class MockProvider(AIProvider):
    name = MOCK_PROVIDER_NAME

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(name=self.name, streaming=True, tool_calls=True, enabled=True)

    def generate(self, request: GenerateRequest) -> GenerateResult:
        content, tool_call = self._compose(request)
        if tool_call is not None:
            return GenerateResult(content="", tool_calls=[tool_call], finish_reason=ProviderFinishReason.TOOL_CALLS)
        return GenerateResult(
            content=content,
            finish_reason=ProviderFinishReason.STOP,
            provider_message_id=f"mock-{_deterministic_id(content)}",
        )

    def stream(self, request: GenerateRequest) -> Iterator[StreamChunk]:
        content, tool_call = self._compose(request)
        if tool_call is not None:
            yield StreamChunk(tool_calls=[tool_call], finish_reason=ProviderFinishReason.TOOL_CALLS)
            return

        words = content.split(" ") if content else []
        if not words:
            yield StreamChunk(delta="", finish_reason=ProviderFinishReason.STOP)
            return

        chunk_size = 4
        for start in range(0, len(words), chunk_size):
            piece = " ".join(words[start : start + chunk_size])
            is_last = start + chunk_size >= len(words)
            delta = piece if start == 0 else " " + piece
            yield StreamChunk(
                delta=delta,
                finish_reason=ProviderFinishReason.STOP if is_last else None,
                provider_message_id=f"mock-{_deterministic_id(content)}" if is_last else None,
            )

    def summarize(self, context: ConversationContext) -> SummaryResult:
        qualification = context.qualification
        if qualification.collected_data:
            summary = (
                f"Test conversation with {context.receptionist_name} for {context.business_name}. "
                f"Captured {len(qualification.collected_data)} field(s): "
                f"{', '.join(sorted(qualification.collected_data.keys()))}."
            )
        else:
            summary = (
                f"Test conversation with {context.receptionist_name} for {context.business_name}. "
                "No qualification data was captured."
            )
        if qualification.qualification_complete:
            summary += " Qualification is complete."
        else:
            summary += " Qualification is not yet complete."

        return SummaryResult(
            summary=summary,
            captured_requirements=dict(qualification.collected_data),
            unresolved_questions=[field.label for field in qualification.missing_field_summaries],
            recommended_next_action=context.recommended_next_action,
        )

    def _compose(self, request: GenerateRequest) -> tuple[str, ToolCallRequest | None]:
        context = request.context

        if context.safety.triggered:
            return context.safety.fixed_response or "I'm not able to help with that here.", None

        latest_user_text = _latest_user_message(request.messages)

        if not context.tool_results and request.tools:
            tool_name = _decide_tool(
                latest_user_text,
                {tool.name for tool in request.tools},
                has_sources=bool(context.retrieved_sources),
            )
            if tool_name is not None:
                call_id = f"call-{_deterministic_id(tool_name, latest_user_text, str(context.turn_index))}"
                arguments = _tool_arguments(tool_name, latest_user_text)
                return "", ToolCallRequest(id=call_id, name=tool_name, arguments=arguments)

        parts: list[str] = []
        acknowledgment = _acknowledgment(context.qualification)
        if acknowledgment:
            parts.append(acknowledgment)

        rejection = _rejection_note(context.qualification)
        if rejection:
            parts.append(rejection)

        answer = _compose_answer(latest_user_text, context.retrieved_sources, context.tool_results)
        if answer:
            parts.append(answer)

        if context.qualification.next_field is not None:
            parts.append(_question_for_field(context.qualification.next_field))
        elif context.qualification.qualification_complete and context.recommended_next_action:
            parts.append(_next_action_offer(context.recommended_next_action))

        if not parts:
            parts.append("How can I help you today?")

        return " ".join(parts), None
