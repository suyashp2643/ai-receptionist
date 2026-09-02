from app.ai.providers.base import QualificationFieldSummary
from app.ai.qualification import extract_value_for_field, process_message, to_field_summary
from app.schemas.qualification import QualificationField, QualificationFieldOption


def _field(key: str, field_type: str, *, options: list[dict] | None = None) -> QualificationFieldSummary:
    return QualificationFieldSummary(key=key, label=key.replace("_", " ").title(), type=field_type, options=options)


class TestEmailExtraction:
    def test_extracts_a_valid_email_from_a_sentence(self):
        value, reason = extract_value_for_field(_field("email", "email"), "sure, it's ada@example.com thanks!")
        assert value == "ada@example.com"
        assert reason is None

    def test_normalizes_to_lowercase(self):
        value, _ = extract_value_for_field(_field("email", "email"), "ADA@EXAMPLE.COM")
        assert value == "ada@example.com"

    def test_rejects_text_with_no_email(self):
        value, reason = extract_value_for_field(_field("email", "email"), "I don't want to share that")
        assert value is None
        assert reason is not None


class TestPhoneExtraction:
    def test_extracts_and_normalizes_a_phone_number(self):
        value, _ = extract_value_for_field(_field("phone", "phone"), "you can reach me at +1 (415) 555-0134")
        assert value == "+14155550134"

    def test_rejects_a_number_too_short_to_be_a_real_phone_number(self):
        value, reason = extract_value_for_field(_field("phone", "phone"), "call me at 555")
        assert value is None
        assert reason is not None


class TestNumberAndCurrency:
    def test_extracts_a_plain_number(self):
        value, _ = extract_value_for_field(_field("guests", "number"), "we'll have 4 people")
        assert value == 4.0

    def test_extracts_a_currency_amount(self):
        value, _ = extract_value_for_field(_field("budget", "currency"), "my budget is around $450,000")
        assert value == 450000.0

    def test_rejects_when_no_number_present(self):
        value, reason = extract_value_for_field(_field("guests", "number"), "not sure yet")
        assert value is None
        assert reason is not None


class TestDateTimeExtraction:
    def test_extracts_iso_date(self):
        value, _ = extract_value_for_field(_field("move_in", "date"), "2026-03-15 works for me")
        assert value == "2026-03-15"

    def test_extracts_slash_date(self):
        value, _ = extract_value_for_field(_field("move_in", "date"), "how about 03/15/2026")
        assert value == "2026-03-15"

    def test_rejects_an_invalid_calendar_date(self):
        value, reason = extract_value_for_field(_field("move_in", "date"), "2026-02-30")
        assert value is None
        assert reason is not None

    def test_extracts_24h_time(self):
        value, _ = extract_value_for_field(_field("call_time", "time"), "call me at 14:30")
        assert value == "14:30"

    def test_extracts_12h_time_with_period(self):
        value, _ = extract_value_for_field(_field("call_time", "time"), "how about 2:30pm")
        assert value == "14:30"

    def test_extracts_noon_correctly(self):
        value, _ = extract_value_for_field(_field("call_time", "time"), "12pm works")
        assert value == "12:00"

    def test_datetime_requires_both_date_and_time(self):
        value, reason = extract_value_for_field(_field("appt", "datetime"), "2026-03-15")
        assert value is None
        assert reason is not None
        value2, _ = extract_value_for_field(_field("appt", "datetime"), "2026-03-15 at 14:30")
        assert value2 == "2026-03-15T14:30"


class TestConsent:
    def test_explicit_yes_is_accepted(self):
        value, _ = extract_value_for_field(_field("consent", "boolean"), "yes")
        assert value is True

    def test_explicit_no_is_accepted(self):
        value, _ = extract_value_for_field(_field("consent", "boolean"), "no")
        assert value is False

    def test_ambiguous_text_never_infers_consent(self):
        value, reason = extract_value_for_field(_field("consent", "boolean"), "sounds good, sure whatever works")
        assert value is None
        assert reason is None  # not a rejection either — just "not yet answered"

    def test_a_sentence_that_merely_contains_yes_is_not_treated_as_consent(self):
        value, _ = extract_value_for_field(_field("consent", "boolean"), "yes I have a question about pricing")
        assert value is None


class TestSelectFields:
    _options = [{"value": "under_300k", "label": "Under $300k"}, {"value": "over_300k", "label": "Over $300k"}]

    def test_matches_by_label(self):
        value, _ = extract_value_for_field(_field("budget", "single_select", options=self._options), "Under $300k")
        assert value == "under_300k"

    def test_matches_by_numeric_index(self):
        value, _ = extract_value_for_field(_field("budget", "single_select", options=self._options), "2")
        assert value == "over_300k"

    def test_rejects_a_value_not_in_the_options(self):
        field = _field("budget", "single_select", options=self._options)
        value, reason = extract_value_for_field(field, "a million dollars")
        assert value is None
        assert reason is not None

    def test_multi_select_matches_several_values(self):
        options = [
            {"value": "email", "label": "Email"},
            {"value": "phone", "label": "Phone"},
            {"value": "text", "label": "Text"},
        ]
        field = _field("contact_methods", "multi_select", options=options)
        value, _ = extract_value_for_field(field, "email and phone")
        assert value == ["email", "phone"]

    def test_multi_select_rejects_if_any_part_is_unmatched(self):
        options = [{"value": "email", "label": "Email"}, {"value": "phone", "label": "Phone"}]
        field = _field("contact_methods", "multi_select", options=options)
        value, reason = extract_value_for_field(field, "email and carrier pigeon")
        assert value is None
        assert reason is not None


class TestTextFields:
    def test_short_text_is_captured_directly(self):
        value, _ = extract_value_for_field(_field("name", "short_text"), "Ada Lovelace")
        assert value == "Ada Lovelace"

    def test_short_text_rejects_html(self):
        value, reason = extract_value_for_field(_field("name", "short_text"), "<script>alert(1)</script>")
        assert value is None
        assert reason is not None

    def test_long_text_requires_a_minimum_length(self):
        value, reason = extract_value_for_field(_field("notes", "long_text"), "ok")
        assert value is None
        assert reason is None  # too short to be "safely attributable" — not a rejection, just no attempt

    def test_long_text_captures_a_substantive_answer(self):
        text = "I'm looking for a three bedroom house near the downtown area with a large backyard."
        value, _ = extract_value_for_field(_field("notes", "long_text"), text)
        assert value == text


class TestScopedExtractionSafety:
    """The core safety property: a value is only ever attempted for the
    field currently being asked about — never scanned for across the
    whole message looking for any field-shaped text."""

    def test_an_email_mentioned_while_a_different_field_is_pending_is_not_captured(self):
        phone_field = _field("phone", "phone")
        outcome = process_message(
            all_fields=[phone_field, _field("email", "email")],
            pending_field=phone_field,
            collected_data={},
            raw_message="by the way my email is ada@example.com but here's my number +14155550134",
        )
        assert outcome.captured == {"phone": "+14155550134"}
        assert "email" not in outcome.captured


class TestCorrections:
    def test_explicit_correction_updates_an_already_captured_field(self):
        email_field = _field("email", "email")
        outcome = process_message(
            all_fields=[email_field],
            pending_field=None,
            collected_data={"email": "old@example.com"},
            raw_message="actually my email is new@example.com",
        )
        assert outcome.corrected == {"email": "new@example.com"}
        assert outcome.captured == {}

    def test_no_correction_trigger_phrase_means_no_correction_even_if_a_pattern_matches(self):
        email_field = _field("email", "email")
        outcome = process_message(
            all_fields=[email_field],
            pending_field=None,
            collected_data={"email": "old@example.com"},
            raw_message="you can also reach new@example.com if needed",
        )
        assert outcome.corrected == {}

    def test_ambiguous_correction_across_two_matching_fields_is_not_applied(self):
        phone_field = _field("phone", "phone")
        alt_phone_field = _field("alt_phone", "phone")
        outcome = process_message(
            all_fields=[phone_field, alt_phone_field],
            pending_field=None,
            collected_data={"phone": "+14155550100", "alt_phone": "+14155550101"},
            raw_message="actually call +14155559999 instead",
        )
        # Both phone-typed fields match the same pattern — ambiguous, so no
        # correction is silently guessed.
        assert outcome.corrected == {}


class TestUndefinedFieldsIgnored:
    def test_process_message_never_captures_a_field_outside_all_fields(self):
        known_field = _field("email", "email")
        outcome = process_message(
            all_fields=[known_field], pending_field=known_field, collected_data={}, raw_message="ada@example.com"
        )
        assert set(outcome.captured.keys()) <= {"email"}


class TestFieldSummaryAdapter:
    def test_to_field_summary_preserves_options(self):
        field_def = QualificationField(
            key="budget",
            label="Budget",
            type="single_select",
            required=True,
            display_order=0,
            options=[
                QualificationFieldOption(value="low", label="Low"),
                QualificationFieldOption(value="high", label="High"),
            ],
        )
        summary = to_field_summary(field_def)
        assert summary.key == "budget"
        assert summary.options == [{"value": "low", "label": "Low"}, {"value": "high", "label": "High"}]
