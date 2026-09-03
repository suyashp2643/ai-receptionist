import uuid
from datetime import UTC, date, datetime, timedelta

from app.config import get_settings
from app.models.appointment_request import AppointmentRequest
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.enquiry import Enquiry
from app.models.enums import (
    AppointmentRequestStatus,
    ConversationChannel,
    ConversationMessageRole,
    ConversationMode,
    ConversationStatus,
    HandoffStatus,
)
from app.models.human_handoff import HumanHandoff
from app.models.widget_installation import WidgetInstallation
from app.models.widget_visitor_session import WidgetVisitorSession
from app.services import analytics_service
from app.services.analytics_service import InvalidAnalyticsRangeError
from sqlalchemy.orm import Session

from tests.factories import make_receptionist, make_tenant_with_owner

settings = get_settings()


def _make_conversation(
    db: Session,
    *,
    tenant_id,
    receptionist_id,
    mode=ConversationMode.WIDGET,
    started_at=None,
    status=ConversationStatus.ACTIVE,
) -> Conversation:
    conv = Conversation(
        tenant_id=tenant_id,
        receptionist_id=receptionist_id,
        mode=mode,
        channel=ConversationChannel.WIDGET if mode == ConversationMode.WIDGET else ConversationChannel.DASHBOARD_TEST,
        provider="mock",
        status=status,
        started_at=started_at or datetime.now(UTC),
    )
    db.add(conv)
    db.flush()
    return conv


def _make_session(
    db: Session, *, tenant_id, receptionist_id, conversation_id, is_platform_preview: bool
) -> WidgetVisitorSession:
    installation = WidgetInstallation(tenant_id=tenant_id, receptionist_id=receptionist_id)
    db.add(installation)
    db.flush()
    session = WidgetVisitorSession(
        tenant_id=tenant_id,
        widget_installation_id=installation.id,
        conversation_id=conversation_id,
        token_hash=uuid.uuid4().hex,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        is_platform_preview=is_platform_preview,
    )
    db.add(session)
    db.flush()
    return session


class TestResolvePeriod:
    def test_today_preset_uses_tenant_timezone(self, db_session: Session):
        period = analytics_service.resolve_period(
            preset="today", tenant_timezone="Pacific/Auckland", custom_start=None, custom_end=None, max_range_days=366
        )
        assert period.start_date == period.end_date

    def test_custom_range_requires_both_dates(self, db_session: Session):
        try:
            analytics_service.resolve_period(
                preset="custom", tenant_timezone="UTC", custom_start=None, custom_end=None, max_range_days=366
            )
            raise AssertionError("expected InvalidAnalyticsRangeError")
        except InvalidAnalyticsRangeError:
            pass

    def test_range_exceeding_max_is_rejected(self, db_session: Session):
        try:
            analytics_service.resolve_period(
                preset="custom",
                tenant_timezone="UTC",
                custom_start=date(2020, 1, 1),
                custom_end=date(2021, 1, 1),
                max_range_days=30,
            )
            raise AssertionError("expected InvalidAnalyticsRangeError")
        except InvalidAnalyticsRangeError:
            pass

    def test_end_before_start_is_rejected(self, db_session: Session):
        try:
            analytics_service.resolve_period(
                preset="custom",
                tenant_timezone="UTC",
                custom_start=date(2026, 3, 2),
                custom_end=date(2026, 3, 1),
                max_range_days=366,
            )
            raise AssertionError("expected InvalidAnalyticsRangeError")
        except InvalidAnalyticsRangeError:
            pass

    def test_unrecognized_timezone_is_rejected(self, db_session: Session):
        try:
            analytics_service.resolve_period(
                preset="today", tenant_timezone="Not/AZone", custom_start=None, custom_end=None, max_range_days=366
            )
            raise AssertionError("expected InvalidAnalyticsRangeError")
        except InvalidAnalyticsRangeError:
            pass


class TestOverviewMetrics:
    def _period(self):
        return analytics_service.resolve_period(
            preset="custom",
            tenant_timezone="UTC",
            custom_start=date(2026, 1, 1),
            custom_end=date(2026, 1, 31),
            max_range_days=366,
        )

    def test_zero_denominators_are_safe(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        overview = analytics_service.get_overview(
            db_session,
            tenant_id=tenant.id,
            period=self._period(),
            receptionist_id=None,
            include_test_preview=False,
            settings=settings,
        )
        assert overview["total_conversations"] == 0
        assert overview["contact_capture_rate"] is None
        assert overview["qualification_completion_rate"] is None
        assert overview["conversation_completion_rate"] is None
        assert overview["average_first_response_time_seconds"] is None
        assert overview["average_conversation_length_messages"] is None
        assert overview["estimated_staff_time_saved_minutes"] == 0.0

    def test_source_classification_excludes_test_and_preview_by_default(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        in_range = datetime(2026, 1, 15, tzinfo=UTC)

        widget_conv = _make_conversation(
            db_session,
            tenant_id=tenant.id,
            receptionist_id=receptionist.id,
            mode=ConversationMode.WIDGET,
            started_at=in_range,
        )
        _make_session(
            db_session,
            tenant_id=tenant.id,
            receptionist_id=receptionist.id,
            conversation_id=widget_conv.id,
            is_platform_preview=False,
        )

        preview_conv = _make_conversation(
            db_session,
            tenant_id=tenant.id,
            receptionist_id=receptionist.id,
            mode=ConversationMode.WIDGET,
            started_at=in_range,
        )
        _make_session(
            db_session,
            tenant_id=tenant.id,
            receptionist_id=receptionist.id,
            conversation_id=preview_conv.id,
            is_platform_preview=True,
        )

        _make_conversation(
            db_session,
            tenant_id=tenant.id,
            receptionist_id=receptionist.id,
            mode=ConversationMode.TEST,
            started_at=in_range,
        )

        default_overview = analytics_service.get_overview(
            db_session,
            tenant_id=tenant.id,
            period=self._period(),
            receptionist_id=None,
            include_test_preview=False,
            settings=settings,
        )
        assert default_overview["total_conversations"] == 1
        assert default_overview["genuine_widget_conversations"] == 1
        assert default_overview["preview_conversations"] == 1
        assert default_overview["test_conversations"] == 1

        included_overview = analytics_service.get_overview(
            db_session,
            tenant_id=tenant.id,
            period=self._period(),
            receptionist_id=None,
            include_test_preview=True,
            settings=settings,
        )
        assert included_overview["total_conversations"] == 3

    def test_receptionist_filter_isolates_counts(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        r1, _ = make_receptionist(db_session, tenant=tenant, name="R1")
        r2, _ = make_receptionist(db_session, tenant=tenant, name="R2")
        in_range = datetime(2026, 1, 15, tzinfo=UTC)

        c1 = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=r1.id, started_at=in_range)
        _make_session(
            db_session, tenant_id=tenant.id, receptionist_id=r1.id, conversation_id=c1.id, is_platform_preview=False
        )
        c2 = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=r2.id, started_at=in_range)
        _make_session(
            db_session, tenant_id=tenant.id, receptionist_id=r2.id, conversation_id=c2.id, is_platform_preview=False
        )

        overview = analytics_service.get_overview(
            db_session,
            tenant_id=tenant.id,
            period=self._period(),
            receptionist_id=r1.id,
            include_test_preview=False,
            settings=settings,
        )
        assert overview["total_conversations"] == 1

    def test_date_range_excludes_conversations_outside_window(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        outside = datetime(2026, 2, 15, tzinfo=UTC)
        conv = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id, started_at=outside)
        _make_session(
            db_session,
            tenant_id=tenant.id,
            receptionist_id=receptionist.id,
            conversation_id=conv.id,
            is_platform_preview=False,
        )

        overview = analytics_service.get_overview(
            db_session,
            tenant_id=tenant.id,
            period=self._period(),
            receptionist_id=None,
            include_test_preview=False,
            settings=settings,
        )
        assert overview["total_conversations"] == 0

    def test_contact_capture_rate_and_qualification_rate(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        in_range = datetime(2026, 1, 15, tzinfo=UTC)

        conv1 = _make_conversation(
            db_session, tenant_id=tenant.id, receptionist_id=receptionist.id, started_at=in_range
        )
        _make_session(
            db_session,
            tenant_id=tenant.id,
            receptionist_id=receptionist.id,
            conversation_id=conv1.id,
            is_platform_preview=False,
        )
        conv2 = _make_conversation(
            db_session, tenant_id=tenant.id, receptionist_id=receptionist.id, started_at=in_range
        )
        _make_session(
            db_session,
            tenant_id=tenant.id,
            receptionist_id=receptionist.id,
            conversation_id=conv2.id,
            is_platform_preview=False,
        )

        db_session.add(Contact(tenant_id=tenant.id, conversation_id=conv1.id, name="Pat", created_at=in_range))
        db_session.add(
            Enquiry(
                tenant_id=tenant.id,
                receptionist_id=receptionist.id,
                conversation_id=conv1.id,
                qualification_complete=True,
                created_at=in_range,
            )
        )
        db_session.add(
            Enquiry(
                tenant_id=tenant.id,
                receptionist_id=receptionist.id,
                conversation_id=conv2.id,
                qualification_complete=False,
                created_at=in_range,
            )
        )
        db_session.flush()

        overview = analytics_service.get_overview(
            db_session,
            tenant_id=tenant.id,
            period=self._period(),
            receptionist_id=None,
            include_test_preview=False,
            settings=settings,
        )
        assert overview["contacts_captured"] == 1
        assert overview["contact_capture_rate"] == 0.5
        assert overview["enquiries_created"] == 2
        assert overview["qualified_enquiries"] == 1
        assert overview["qualification_completion_rate"] == 0.5

    def test_appointment_and_handoff_status_counts(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        in_range = datetime(2026, 1, 15, tzinfo=UTC)
        conv = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id, started_at=in_range)
        _make_session(
            db_session,
            tenant_id=tenant.id,
            receptionist_id=receptionist.id,
            conversation_id=conv.id,
            is_platform_preview=False,
        )

        db_session.add(
            AppointmentRequest(
                tenant_id=tenant.id,
                receptionist_id=receptionist.id,
                conversation_id=conv.id,
                requested_date=date(2026, 2, 1),
                timezone="UTC",
                status=AppointmentRequestStatus.PENDING,
                created_at=in_range,
            )
        )
        db_session.add(
            AppointmentRequest(
                tenant_id=tenant.id,
                receptionist_id=receptionist.id,
                conversation_id=conv.id,
                requested_date=date(2026, 2, 2),
                timezone="UTC",
                status=AppointmentRequestStatus.CONFIRMED,
                created_at=in_range,
            )
        )
        db_session.add(
            HumanHandoff(
                tenant_id=tenant.id,
                receptionist_id=receptionist.id,
                conversation_id=conv.id,
                reason="test",
                status=HandoffStatus.OPEN,
                created_at=in_range,
            )
        )
        db_session.flush()

        overview = analytics_service.get_overview(
            db_session,
            tenant_id=tenant.id,
            period=self._period(),
            receptionist_id=None,
            include_test_preview=False,
            settings=settings,
        )
        assert overview["appointment_requests"] == 2
        assert overview["pending_appointments"] == 1
        assert overview["confirmed_appointments"] == 1
        assert overview["human_handoffs"] == 1
        assert overview["open_handoffs"] == 1

    def test_safety_and_fallback_counts(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        in_range = datetime(2026, 1, 15, tzinfo=UTC)
        conv = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id, started_at=in_range)
        conv.had_safety_event = True
        _make_session(
            db_session,
            tenant_id=tenant.id,
            receptionist_id=receptionist.id,
            conversation_id=conv.id,
            is_platform_preview=False,
        )
        db_session.add(
            ConversationMessage(
                tenant_id=tenant.id,
                conversation_id=conv.id,
                role=ConversationMessageRole.ASSISTANT,
                content="I don't have that information available right now, and I don't want to guess.",
                sequence_number=0,
                is_fallback_response=True,
            )
        )
        db_session.flush()

        overview = analytics_service.get_overview(
            db_session,
            tenant_id=tenant.id,
            period=self._period(),
            receptionist_id=None,
            include_test_preview=False,
            settings=settings,
        )
        assert overview["safety_interventions"] == 1
        assert overview["unanswered_or_fallback_responses"] == 1

    def test_estimated_time_saved_is_labeled_and_grounded(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        in_range = datetime(2026, 1, 15, tzinfo=UTC)
        for _ in range(3):
            conv = _make_conversation(
                db_session, tenant_id=tenant.id, receptionist_id=receptionist.id, started_at=in_range
            )
            _make_session(
                db_session,
                tenant_id=tenant.id,
                receptionist_id=receptionist.id,
                conversation_id=conv.id,
                is_platform_preview=False,
            )

        overview = analytics_service.get_overview(
            db_session,
            tenant_id=tenant.id,
            period=self._period(),
            receptionist_id=None,
            include_test_preview=False,
            settings=settings,
        )
        assert overview["genuine_widget_conversations"] == 3
        assert overview["estimated_staff_time_saved_minutes"] == 3 * settings.estimated_staff_minutes_per_conversation
        assert overview["estimated_staff_time_saved_minutes_is_estimate"] is True


class TestTimeseries:
    def test_buckets_by_calendar_day_in_tenant_timezone(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        period = analytics_service.resolve_period(
            preset="custom",
            tenant_timezone="UTC",
            custom_start=date(2026, 1, 1),
            custom_end=date(2026, 1, 3),
            max_range_days=366,
        )
        conv = _make_conversation(
            db_session,
            tenant_id=tenant.id,
            receptionist_id=receptionist.id,
            started_at=datetime(2026, 1, 2, 10, tzinfo=UTC),
        )
        _make_session(
            db_session,
            tenant_id=tenant.id,
            receptionist_id=receptionist.id,
            conversation_id=conv.id,
            is_platform_preview=False,
        )

        points = analytics_service.get_timeseries(
            db_session,
            tenant_id=tenant.id,
            period=period,
            tenant_timezone="UTC",
            receptionist_id=None,
            include_test_preview=False,
        )
        assert len(points) == 3
        by_date = {p["date"]: p["conversations"] for p in points}
        assert by_date["2026-01-01"] == 0
        assert by_date["2026-01-02"] == 1
        assert by_date["2026-01-03"] == 0
