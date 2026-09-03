"""Regression tests for a Phase 7 remediation round: the mock provider's
response composition (app/ai/providers/mock.py) previously (a) echoed a
qualification field's raw, sometimes question-phrased *label* back as if
it were the captured answer ("Got it — I've noted your What service do
you need?."), and (b) always surfaced a field-rejection note even when
the same message produced a genuine, unrelated answer from tools/FAQ
content, reading as self-contradictory next to that answer, and stacked a
redundant "That doesn't look like a valid X" lead-in on top of a `reason`
string that was already a complete sentence.

Unit tests below exercise the composition helpers directly across every
qualification field type; the `TestExactHotelScenario`/`TestClinicScenario`
classes reproduce the exact reported conversations end-to-end through the
real API, the same way the bug was originally found."""

import json
import uuid

from app.ai.providers.base import (
    QualificationFieldSummary,
    QualificationRejection,
    QualificationState,
)
from app.ai.providers.mock import _acknowledgment, _format_captured_value, _rejection_note
from app.config import get_settings
from app.core.security import create_access_token
from app.models.enums import ReceptionistStatus
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import make_receptionist, make_tenant_with_owner

settings = get_settings()

_HOTEL_FIELDS = [
    {"key": "checkin_date", "label": "Check-in date", "type": "date", "required": True, "display_order": 0},
]

_CLINIC_FIELDS = [
    {
        "key": "patient_type",
        "label": "Are you a new or existing patient?",
        "type": "single_select",
        "required": True,
        "display_order": 0,
        "options": [{"value": "new", "label": "New patient"}, {"value": "existing", "label": "Existing patient"}],
    },
]


def _auth_headers(user) -> dict[str, str]:
    token, _ = create_access_token(settings=settings, user_id=user.id, session_id=uuid.uuid4())
    return {"Authorization": f"Bearer {token}"}


def _setup_active_receptionist(db_session: Session, tenant, *, qualification_fields, enabled_actions=None):
    receptionist, workflow = make_receptionist(db_session, tenant=tenant)
    receptionist.status = ReceptionistStatus.ACTIVE
    workflow.qualification_schema = {"fields": qualification_fields}
    if enabled_actions is not None:
        workflow.enabled_actions = enabled_actions
    db_session.flush()
    return receptionist, workflow


def _parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        event_name = None
        data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:") :].strip())
        if event_name is not None:
            events.append({"event": event_name, "data": data})
    return events


def _send_message(client: TestClient, tenant_id, conversation_id, headers, content: str):
    response = client.post(
        f"/api/v1/tenants/{tenant_id}/test-conversations/{conversation_id}/messages",
        json={"content": content},
        headers=headers,
    )
    return response, _parse_sse(response.text)


def _start_conversation(client: TestClient, tenant_id, receptionist_id, headers):
    response = client.post(
        f"/api/v1/tenants/{tenant_id}/receptionists/{receptionist_id}/test-conversations", json={}, headers=headers
    )
    return response.json()["id"]


class TestFormatCapturedValueAcrossFieldTypes:
    """Every qualification field type must render naturally in an
    acknowledgment, using only the actually-captured value — never an
    internal key, never a fabricated detail."""

    def test_single_select_uses_the_options_label_not_the_raw_value(self):
        field = QualificationFieldSummary(
            key="patient_type",
            label="Are you a new or existing patient?",
            type="single_select",
            options=[{"value": "new", "label": "New patient"}, {"value": "existing", "label": "Existing patient"}],
        )
        assert _format_captured_value(field, "new") == "New patient"

    def test_multi_select_joins_option_labels(self):
        field = QualificationFieldSummary(
            key="interests",
            label="Interests",
            type="multi_select",
            options=[{"value": "spa", "label": "Spa"}, {"value": "gym", "label": "Gym"}],
        )
        assert _format_captured_value(field, ["spa", "gym"]) == "Spa, Gym"

    def test_boolean_renders_as_yes_or_no(self):
        field = QualificationFieldSummary(key="consent", label="Consent", type="boolean")
        assert _format_captured_value(field, True) == "yes"
        assert _format_captured_value(field, False) == "no"

    def test_email_renders_the_captured_address(self):
        field = QualificationFieldSummary(key="email", label="Email address", type="email")
        assert _format_captured_value(field, "ada@example.com") == "ada@example.com"

    def test_phone_renders_the_captured_number(self):
        field = QualificationFieldSummary(key="phone", label="Phone number", type="phone")
        assert _format_captured_value(field, "+15551234567") == "+15551234567"

    def test_number_renders_the_captured_value(self):
        field = QualificationFieldSummary(key="guests", label="Number of guests", type="number")
        assert _format_captured_value(field, 3.0) == "3.0"

    def test_date_renders_the_captured_value(self):
        field = QualificationFieldSummary(key="checkin_date", label="Check-in date", type="date")
        assert _format_captured_value(field, "2026-09-10") == "2026-09-10"

    def test_short_text_is_truncated_and_quoted_when_long(self):
        field = QualificationFieldSummary(key="notes", label="Notes", type="short_text")
        long_value = "x" * 100
        result = _format_captured_value(field, long_value)
        # Truncated core (60 chars) plus the two quote marks free text is
        # always wrapped in — see _format_captured_value's docstring.
        assert len(result) <= 62
        assert result.startswith('"') and result.endswith('…"')

    def test_short_text_is_quoted_and_does_not_double_a_trailing_period(self):
        field = QualificationFieldSummary(key="service_required", label="What service do you need?", type="short_text")
        result = _format_captured_value(field, "I need an appointment tomorrow.")
        assert result == '"I need an appointment tomorrow"'
        assert ".." not in result


class TestAcknowledgment:
    def test_capture_never_echoes_the_raw_question_phrased_label(self):
        field = QualificationFieldSummary(key="service_required", label="What service do you need?", type="short_text")
        state = QualificationState(collected_data={"service_required": "general checkup"}, just_captured=[field])
        note = _acknowledgment(state)
        assert note is not None
        assert "What service do you need?" not in note
        assert "service_required" not in note
        assert "general checkup" in note

    def test_capture_never_discloses_the_internal_field_key(self):
        field = QualificationFieldSummary(key="checkin_date", label="Check-in date", type="date")
        state = QualificationState(collected_data={"checkin_date": "2026-09-10"}, just_captured=[field])
        note = _acknowledgment(state)
        assert note is not None
        assert "checkin_date" not in note

    def test_correction_is_phrased_distinctly_from_a_fresh_capture(self):
        field = QualificationFieldSummary(key="checkin_date", label="Check-in date", type="date")
        captured = _acknowledgment(
            QualificationState(collected_data={"checkin_date": "2026-09-10"}, just_captured=[field])
        )
        corrected = _acknowledgment(
            QualificationState(collected_data={"checkin_date": "2026-09-12"}, just_corrected=[field])
        )
        assert captured != corrected
        assert "2026-09-10" in captured
        assert "2026-09-12" in corrected
        # A correction must read as a change, not a brand new answer.
        assert "updated" in corrected.lower()

    def test_nothing_captured_or_corrected_produces_no_note(self):
        assert _acknowledgment(QualificationState()) is None


class TestRejectionNote:
    def test_is_a_single_concise_sentence_with_no_redundant_lead_in(self):
        state = QualificationState(
            just_rejected=[
                QualificationRejection(
                    field_key="checkin_date",
                    field_label="Check-in date",
                    reason="I couldn't find a valid date in that (try YYYY-MM-DD).",
                )
            ]
        )
        note = _rejection_note(state)
        # The old behavior produced "That doesn't look like a valid Check-in
        # date — I couldn't find a valid date in that..." — two overlapping
        # "this isn't valid" phrases stacked together.
        assert note == "I couldn't find a valid date in that (try YYYY-MM-DD)."
        assert note.lower().count("doesn't look like") + note.lower().count("valid") <= 1 or "valid" in note

    def test_no_rejection_produces_no_note(self):
        assert _rejection_note(QualificationState()) is None


class TestExactHotelScenario:
    """Reproduces the exact reported defect: a pending `date` field, and a
    natural free-text reply that doesn't match it."""

    def test_three_nights_produces_one_clean_correction_and_the_next_question(
        self, db_backed_client: TestClient, db_session: Session
    ):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _setup_active_receptionist(db_session, tenant, qualification_fields=_HOTEL_FIELDS)
        headers = _auth_headers(owner)
        conversation_id = _start_conversation(db_backed_client, tenant.id, receptionist.id, headers)

        _, events = _send_message(
            db_backed_client, tenant.id, conversation_id, headers, "I'd like to stay for three nights"
        )
        completed = next(e for e in events if e["event"] == "response.completed")
        content = completed["data"]["content"]

        # Exactly one correction phrase, not the doubled "doesn't look like
        # a valid X — I couldn't find a valid X" wording.
        assert content.count("doesn't look like") == 0
        assert content.count("couldn't find a valid date") == 1
        assert "Check-in date" in content or "check-in date" in content.lower()

        state = next(e for e in events if e["event"] == "conversation.updated")["data"]
        # Never silently stored under the wrong field.
        assert "checkin_date" not in state["collected_data"]
        assert state["qualification_complete"] is False

    def test_a_valid_date_is_captured_and_acknowledged_naturally(
        self, db_backed_client: TestClient, db_session: Session
    ):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _setup_active_receptionist(db_session, tenant, qualification_fields=_HOTEL_FIELDS)
        headers = _auth_headers(owner)
        conversation_id = _start_conversation(db_backed_client, tenant.id, receptionist.id, headers)

        _, events = _send_message(db_backed_client, tenant.id, conversation_id, headers, "2026-09-10")
        completed = next(e for e in events if e["event"] == "response.completed")
        content = completed["data"]["content"]

        assert "2026-09-10" in content
        assert "Check-in date" not in content  # the label is never echoed back
        state = next(e for e in events if e["event"] == "conversation.updated")["data"]
        assert state["collected_data"]["checkin_date"] == "2026-09-10"

    def test_a_genuine_question_suppresses_the_rejection_note(self, db_backed_client: TestClient, db_session: Session):
        """The airport-pickup-style case: a message that fails the pending
        date field AND triggers a real, unrelated answer must not show a
        contradictory "that's not a valid date" note beside that answer."""
        from app.models.faq import FAQ
        from app.repositories.faq import FAQRepository

        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _setup_active_receptionist(
            db_session, tenant, qualification_fields=_HOTEL_FIELDS, enabled_actions=["answer_questions"]
        )
        FAQRepository(db_session, tenant.id).add(
            FAQ(
                tenant_id=tenant.id,
                question="Do you have airport pickup?",
                answer="Yes — a complimentary airport shuttle is available for registered guests.",
            )
        )
        db_session.flush()
        headers = _auth_headers(owner)
        conversation_id = _start_conversation(db_backed_client, tenant.id, receptionist.id, headers)

        _, events = _send_message(db_backed_client, tenant.id, conversation_id, headers, "Do you have airport pickup?")
        completed = next(e for e in events if e["event"] == "response.completed")
        content = completed["data"]["content"]

        assert "doesn't look like" not in content
        assert "couldn't find a valid date" not in content
        assert "airport shuttle" in content


class TestClinicScenario:
    """Reproduces the exact reported defect: a captured single_select
    value acknowledged by echoing the question-phrased field label."""

    def test_select_capture_is_acknowledged_by_the_chosen_options_label(
        self, db_backed_client: TestClient, db_session: Session
    ):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _setup_active_receptionist(db_session, tenant, qualification_fields=_CLINIC_FIELDS)
        headers = _auth_headers(owner)
        conversation_id = _start_conversation(db_backed_client, tenant.id, receptionist.id, headers)

        _, events = _send_message(db_backed_client, tenant.id, conversation_id, headers, "New patient")
        completed = next(e for e in events if e["event"] == "response.completed")
        content = completed["data"]["content"]

        assert "New patient" in content
        assert "Are you a new or existing patient?" not in content
        assert "patient_type" not in content

    def test_emergency_language_is_still_exact_and_unaffected_by_the_composition_fix(
        self, db_backed_client: TestClient, db_session: Session
    ):
        from app.repositories.industry_template import IndustryTemplateRepository
        from app.seed_data.seed_runner import seed_industry_templates

        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, workflow = _setup_active_receptionist(db_session, tenant, qualification_fields=_CLINIC_FIELDS)
        seed_industry_templates(db_session)
        template = IndustryTemplateRepository(db_session).get_latest_active_by_key("clinic")
        receptionist.industry_template_id = template.id
        db_session.flush()
        headers = _auth_headers(owner)
        conversation_id = _start_conversation(db_backed_client, tenant.id, receptionist.id, headers)

        _, events = _send_message(
            db_backed_client, tenant.id, conversation_id, headers, "I have severe chest pain right now"
        )
        completed = next(e for e in events if e["event"] == "response.completed")
        content = completed["data"]["content"]
        assert "911" in content or "emergency" in content.lower()
        assert "not able to assess how serious this is" in content
