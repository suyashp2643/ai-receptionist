import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from app.models.business_location import BusinessLocation
from app.models.conversation import Conversation
from app.models.enums import ConversationChannel, ConversationMode, ConversationStatus
from app.models.service import Service
from app.services.appointment_request_service import (
    MAX_FUTURE_DAYS_ALLOWED,
    InvalidAppointmentRequestError,
    create_appointment_request,
)
from sqlalchemy.orm import Session

from tests.factories import make_receptionist, make_tenant_with_owner


def _make_conversation(db_session: Session, *, tenant_id, receptionist_id) -> Conversation:
    conversation = Conversation(
        tenant_id=tenant_id,
        receptionist_id=receptionist_id,
        mode=ConversationMode.WIDGET,
        channel=ConversationChannel.WIDGET,
        provider="mock",
        status=ConversationStatus.ACTIVE,
        locale="en",
        collected_data={},
        missing_required_fields=[],
        qualification_complete=True,
        safety_state={},
    )
    db_session.add(conversation)
    db_session.flush()
    return conversation


def _base_kwargs(db_session: Session, tenant_id, receptionist_id, conversation_id=None, **overrides):
    if conversation_id is None:
        conversation_id = _make_conversation(db_session, tenant_id=tenant_id, receptionist_id=receptionist_id).id
    kwargs = dict(
        tenant_id=tenant_id,
        receptionist_id=receptionist_id,
        conversation_id=conversation_id,
        contact_id=None,
        location_id=None,
        service_id=None,
        requested_date=datetime.now(UTC).date() + timedelta(days=10),
        requested_time=None,
        requested_time_window="morning",
        timezone="UTC",
        notes=None,
        idempotency_key=None,
    )
    kwargs.update(overrides)
    return kwargs


class TestAppointmentDateValidation:
    def test_today_is_accepted(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        today = datetime.now(ZoneInfo("UTC")).date()

        appointment = create_appointment_request(
            db_session, **_base_kwargs(db_session, tenant.id, receptionist.id, requested_date=today, timezone="UTC")
        )
        assert appointment.requested_date == today

    def test_tomorrow_is_accepted(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        tomorrow = datetime.now(ZoneInfo("UTC")).date() + timedelta(days=1)

        appointment = create_appointment_request(
            db_session, **_base_kwargs(db_session, tenant.id, receptionist.id, requested_date=tomorrow, timezone="UTC")
        )
        assert appointment.requested_date == tomorrow

    def test_yesterday_is_rejected(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        yesterday = datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)

        with pytest.raises(InvalidAppointmentRequestError, match="past"):
            create_appointment_request(
                db_session,
                **_base_kwargs(db_session, tenant.id, receptionist.id, requested_date=yesterday, timezone="UTC"),
            )

    def test_exactly_one_year_out_is_accepted(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        boundary = datetime.now(ZoneInfo("UTC")).date() + timedelta(days=MAX_FUTURE_DAYS_ALLOWED)

        appointment = create_appointment_request(
            db_session, **_base_kwargs(db_session, tenant.id, receptionist.id, requested_date=boundary, timezone="UTC")
        )
        assert appointment.requested_date == boundary

    def test_beyond_one_year_is_rejected(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        beyond = datetime.now(ZoneInfo("UTC")).date() + timedelta(days=MAX_FUTURE_DAYS_ALLOWED + 1)

        with pytest.raises(InvalidAppointmentRequestError, match="too far"):
            create_appointment_request(
                db_session,
                **_base_kwargs(db_session, tenant.id, receptionist.id, requested_date=beyond, timezone="UTC"),
            )

    def test_invalid_timezone_is_rejected(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)

        with pytest.raises(InvalidAppointmentRequestError, match="not a recognized timezone"):
            create_appointment_request(
                db_session,
                **_base_kwargs(db_session, tenant.id, receptionist.id, timezone="Mars/Olympus_Mons"),
            )

    def test_legacy_timezone_alias_is_normalized_and_accepted(self, db_session: Session):
        """Real bug found via live browser testing: a visitor's browser can
        report a legacy IANA alias (Intl.DateTimeFormat().resolvedOptions()
        reported "Asia/Calcutta") that this backend's tzdata build doesn't
        recognize directly — confirmed via zoneinfo.available_timezones()
        and ZoneInfo("Asia/Calcutta") both failing — even though it is a
        real, unambiguous timezone under its canonical name
        ("Asia/Kolkata"). The widget's no-location-selected fallback path
        sends exactly this kind of raw browser-detected string, so it must
        be normalized rather than rejected outright."""
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        today = datetime.now(ZoneInfo("Asia/Kolkata")).date()

        appointment = create_appointment_request(
            db_session,
            **_base_kwargs(
                db_session, tenant.id, receptionist.id, requested_date=today, timezone="Asia/Calcutta"
            ),
        )
        assert appointment.timezone == "Asia/Kolkata"

    def test_unrecognized_non_alias_timezone_is_still_rejected(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)

        with pytest.raises(InvalidAppointmentRequestError, match="not a recognized timezone"):
            create_appointment_request(
                db_session,
                **_base_kwargs(db_session, tenant.id, receptionist.id, timezone="Asia/Definitely_Not_Real"),
            )

    def test_location_timezone_rejects_a_date_that_is_only_past_there(self, db_session: Session):
        """Deterministic, clock-independent proof that the *location's*
        timezone governs the date boundary, not the submitted `timezone`
        field: freeze "now" to a fixed real instant (2026-06-15 23:30 UTC)
        at which Pacific/Auckland (UTC+12 in June, NZ winter — no DST) has
        already rolled over to 2026-06-16, while Pacific/Midway (UTC-11) is
        still on 2026-06-15. Submitting `requested_date=2026-06-15` with the
        Auckland location selected must be rejected as "in the past" — it
        would only be accepted if the code incorrectly fell back to the
        submitted Pacific/Midway timezone instead of the location's."""
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        location = BusinessLocation(tenant_id=tenant.id, name="Auckland Office", timezone="Pacific/Auckland")
        db_session.add(location)
        db_session.flush()

        frozen_instant = datetime(2026, 6, 15, 23, 30, tzinfo=UTC)

        with patch("app.services.appointment_request_service.datetime") as mock_datetime:
            mock_datetime.now.side_effect = lambda tz=None: frozen_instant.astimezone(tz) if tz else frozen_instant

            with pytest.raises(InvalidAppointmentRequestError, match="past"):
                create_appointment_request(
                    db_session,
                    **_base_kwargs(
                        db_session,
                        tenant.id,
                        receptionist.id,
                        requested_date=date(2026, 6, 15),
                        timezone="Pacific/Midway",
                        location_id=location.id,
                    ),
                )

    def test_location_timezone_accepts_its_own_today(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        location = BusinessLocation(tenant_id=tenant.id, name="Auckland Office", timezone="Pacific/Auckland")
        db_session.add(location)
        db_session.flush()

        frozen_instant = datetime(2026, 6, 15, 23, 30, tzinfo=UTC)

        with patch("app.services.appointment_request_service.datetime") as mock_datetime:
            mock_datetime.now.side_effect = lambda tz=None: frozen_instant.astimezone(tz) if tz else frozen_instant

            appointment = create_appointment_request(
                db_session,
                **_base_kwargs(
                    db_session,
                    tenant.id,
                    receptionist.id,
                    requested_date=date(2026, 6, 16),  # Auckland's "today" at the frozen instant
                    timezone="Pacific/Midway",
                    location_id=location.id,
                ),
            )
            assert appointment.requested_date == date(2026, 6, 16)


class TestServiceAndLocationValidation:
    def test_valid_active_service_and_location_are_accepted(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        location = BusinessLocation(tenant_id=tenant.id, name="Main Office", timezone="UTC", is_active=True)
        service = Service(tenant_id=tenant.id, name="Consultation", is_active=True)
        db_session.add_all([location, service])
        db_session.flush()

        appointment = create_appointment_request(
            db_session,
            **_base_kwargs(db_session, tenant.id, receptionist.id, location_id=location.id, service_id=service.id),
        )
        assert appointment.location_id == location.id
        assert appointment.service_id == service.id

    def test_inactive_service_is_rejected(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        service = Service(tenant_id=tenant.id, name="Retired Service", is_active=False)
        db_session.add(service)
        db_session.flush()

        with pytest.raises(InvalidAppointmentRequestError, match="service was not found"):
            create_appointment_request(
                db_session, **_base_kwargs(db_session, tenant.id, receptionist.id, service_id=service.id)
            )

    def test_inactive_location_is_rejected(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        location = BusinessLocation(tenant_id=tenant.id, name="Closed Branch", timezone="UTC", is_active=False)
        db_session.add(location)
        db_session.flush()

        with pytest.raises(InvalidAppointmentRequestError, match="location was not found"):
            create_appointment_request(
                db_session, **_base_kwargs(db_session, tenant.id, receptionist.id, location_id=location.id)
            )

    def test_unknown_service_id_is_rejected(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)

        with pytest.raises(InvalidAppointmentRequestError, match="service was not found"):
            create_appointment_request(
                db_session, **_base_kwargs(db_session, tenant.id, receptionist.id, service_id=uuid.uuid4())
            )

    def test_unknown_location_id_is_rejected(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)

        with pytest.raises(InvalidAppointmentRequestError, match="location was not found"):
            create_appointment_request(
                db_session, **_base_kwargs(db_session, tenant.id, receptionist.id, location_id=uuid.uuid4())
            )

    def test_cross_tenant_service_id_is_rejected(self, db_session: Session):
        tenant_a, _, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        receptionist_a, _ = make_receptionist(db_session, tenant=tenant_a)
        tenant_b, _, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")
        other_service = Service(tenant_id=tenant_b.id, name="Other Tenant's Service", is_active=True)
        db_session.add(other_service)
        db_session.flush()

        with pytest.raises(InvalidAppointmentRequestError, match="service was not found"):
            create_appointment_request(
                db_session, **_base_kwargs(db_session, tenant_a.id, receptionist_a.id, service_id=other_service.id)
            )

    def test_cross_tenant_location_id_is_rejected(self, db_session: Session):
        tenant_a, _, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        receptionist_a, _ = make_receptionist(db_session, tenant=tenant_a)
        tenant_b, _, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")
        other_location = BusinessLocation(tenant_id=tenant_b.id, name="Other Tenant's Office", timezone="UTC")
        db_session.add(other_location)
        db_session.flush()

        with pytest.raises(InvalidAppointmentRequestError, match="location was not found"):
            create_appointment_request(
                db_session, **_base_kwargs(db_session, tenant_a.id, receptionist_a.id, location_id=other_location.id)
            )

    def test_service_restricted_to_a_location_auto_fills_that_location(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        location = BusinessLocation(tenant_id=tenant.id, name="Downtown Branch", timezone="UTC")
        db_session.add(location)
        db_session.flush()
        service = Service(tenant_id=tenant.id, name="In-Branch Only Service", is_active=True, location_id=location.id)
        db_session.add(service)
        db_session.flush()

        appointment = create_appointment_request(
            db_session, **_base_kwargs(db_session, tenant.id, receptionist.id, service_id=service.id)
        )
        assert appointment.location_id == location.id

    def test_service_restricted_to_a_location_rejects_a_conflicting_location(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        correct_location = BusinessLocation(tenant_id=tenant.id, name="Correct Branch", timezone="UTC")
        wrong_location = BusinessLocation(tenant_id=tenant.id, name="Wrong Branch", timezone="UTC")
        db_session.add_all([correct_location, wrong_location])
        db_session.flush()
        service = Service(
            tenant_id=tenant.id, name="Restricted Service", is_active=True, location_id=correct_location.id
        )
        db_session.add(service)
        db_session.flush()

        with pytest.raises(InvalidAppointmentRequestError, match="not offered at the selected location"):
            create_appointment_request(
                db_session,
                **_base_kwargs(
                    db_session, tenant.id, receptionist.id, service_id=service.id, location_id=wrong_location.id
                ),
            )
