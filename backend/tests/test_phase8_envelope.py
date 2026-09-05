import uuid

import pytest
from app.integrations.envelope import (
    ENVELOPE_SCHEMA,
    EVENT_PAYLOAD_TYPES,
    EVENT_TYPE_VERSIONS,
    ConnectionTestEventPayload,
    ContactCapturedPayload,
    ContactSummaryPayload,
    EventEnvelope,
    EventType,
    build_envelope,
)


def _contact_payload() -> ContactCapturedPayload:
    return ContactCapturedPayload(
        contact=ContactSummaryPayload(contact_id=uuid.uuid4(), marketing_consent=False, source="widget")
    )


class TestBuildEnvelope:
    def test_stamps_event_id_type_version_and_source(self):
        tenant_id = uuid.uuid4()
        envelope = build_envelope(EventType.CONTACT_CAPTURED, tenant_id=tenant_id, payload=_contact_payload())
        assert envelope.event_type == EventType.CONTACT_CAPTURED
        assert envelope.event_version == EVENT_TYPE_VERSIONS[EventType.CONTACT_CAPTURED]
        assert envelope.tenant_reference == str(tenant_id)
        assert envelope.source == "ai-receptionist"
        assert isinstance(envelope.event_id, uuid.UUID)

    def test_two_calls_produce_different_event_ids(self):
        tenant_id = uuid.uuid4()
        a = build_envelope(EventType.CONTACT_CAPTURED, tenant_id=tenant_id, payload=_contact_payload())
        b = build_envelope(EventType.CONTACT_CAPTURED, tenant_id=tenant_id, payload=_contact_payload())
        assert a.event_id != b.event_id

    def test_carries_correlation_and_causation_ids(self):
        correlation_id = uuid.uuid4()
        causation_id = uuid.uuid4()
        envelope = build_envelope(
            EventType.CONTACT_CAPTURED,
            tenant_id=uuid.uuid4(),
            payload=_contact_payload(),
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
        assert envelope.correlation_id == correlation_id
        assert envelope.causation_id == causation_id

    def test_rejects_a_payload_for_the_wrong_event_type(self):
        with pytest.raises(TypeError, match="ContactCapturedPayload"):
            build_envelope(
                EventType.CONNECTION_TEST_EVENT,
                tenant_id=uuid.uuid4(),
                payload=_contact_payload(),
            )

    def test_every_event_type_has_a_registered_payload_class(self):
        assert set(EVENT_PAYLOAD_TYPES.keys()) == set(EventType)

    def test_every_event_type_has_a_version(self):
        assert set(EVENT_TYPE_VERSIONS.keys()) == set(EventType)


class TestPayloadStrictness:
    def test_unknown_field_is_rejected(self):
        with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError
            ContactSummaryPayload(
                contact_id=uuid.uuid4(), marketing_consent=False, source="widget", extra_field="not allowed"
            )

    def test_envelope_itself_rejects_an_unknown_field(self):
        envelope = build_envelope(EventType.CONTACT_CAPTURED, tenant_id=uuid.uuid4(), payload=_contact_payload())
        raw = envelope.model_dump(mode="json", by_alias=True)
        raw["not_a_real_field"] = "should be rejected"
        with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError
            EventEnvelope.model_validate(raw)


class TestRoundTrip:
    def test_serialize_then_validate_round_trips(self):
        envelope = build_envelope(
            EventType.CONNECTION_TEST_EVENT,
            tenant_id=uuid.uuid4(),
            payload=ConnectionTestEventPayload(triggered_by="test"),
        )
        raw = envelope.model_dump(mode="json", by_alias=True)
        assert raw["schema"] == ENVELOPE_SCHEMA
        restored = EventEnvelope.model_validate(raw)
        assert restored.event_id == envelope.event_id
        assert restored.event_type == envelope.event_type
        assert restored.data == envelope.data
