"""Tenant-scoped operational analytics. Every number here comes from an
explicit SQL aggregate (COUNT/AVG/FILTER) against the real tables — nothing
is invented, sampled, or hardcoded, and no query here ever loads a full
transcript or every row of a list just to compute a count.

## Metric definitions (numerator / denominator, exactly as displayed)

- **total_conversations**: COUNT(conversations) started in the period,
  filtered by tenant (+ optional receptionist), matching the requested
  source scope (see below).
- **genuine_widget_conversations** / **preview_conversations** /
  **test_conversations**: the same COUNT, partitioned by
  app/core/conversation_source.py's ConversationSource — computed via the
  exact same `source_case_expression` used by the conversation list/detail
  views, so a conversation is never classified two different ways in two
  different places.
- **unique_visitor_sessions**: COUNT(WidgetVisitorSession) whose
  conversation started in the period and matches the source scope. Since a
  WidgetVisitorSession is 1:1 with the conversation it authorizes (see that
  model's docstring), this is currently numerically identical to
  genuine_widget_conversations + preview_conversations combined — exposed
  as its own metric anyway because it is conceptually distinct (a future
  phase could let one session span multiple conversations) and because
  "sessions" is the more familiar term for visitor traffic.
- **contacts_captured**: COUNT(contacts) created in the period. A contact
  whose `conversation_id` is NULL (the conversation that captured it was
  later deleted — no deletion job exists yet, so this should not occur in
  practice) is excluded from the default (test/preview-excluded) count,
  since its source cannot be determined; it is included when
  `include_test_preview=True`.
- **contact_capture_rate**: contacts_captured / genuine_widget_conversations
  (always computed against the *widget* cohort specifically, regardless of
  `include_test_preview`, since "did a real visitor leave contact info" is
  only meaningful for real visitor conversations). `None` when the
  denominator is 0 — never displayed as 0% or NaN.
- **enquiries_created**: COUNT(enquiries) created in the period.
- **qualified_enquiries**: COUNT(enquiries WHERE qualification_complete)
  created in the period.
- **qualification_completion_rate**: qualified_enquiries / enquiries_created.
- **appointment_requests**, **pending_appointments**,
  **confirmed_appointments**: COUNT(appointment_requests) created in the
  period, optionally filtered by status.
- **human_handoffs**, **open_handoffs**, **resolved_handoffs**: same shape
  for human_handoffs.
- **unanswered_or_fallback_responses**: COUNT(conversation_messages WHERE
  is_fallback_response) whose conversation started in the period and
  matches the source scope. Set by the AI provider when it found nothing to
  answer a question with (see app/ai/providers/base.py's GenerateResult and
  app/ai/providers/mock.py's FALLBACK_RESPONSE_MARKERS) — **currently
  meaningful only for the mock provider**; a real LLM provider would need
  its own logic to set this truthfully.
- **safety_interventions**: COUNT(conversations WHERE had_clinic_emergency
  OR had_safety_event, i.e. had_safety_event) started in the period —
  conversation-level, not per-message, since the dashboard cares about "how
  many conversations needed a safety response," not how many times within
  one. Clinic emergencies (`had_clinic_emergency`) are a documented subset,
  surfaced separately in the conversation list/detail, never folded into an
  ordinary handoff.
- **average_first_response_time_seconds**: AVG(seconds from
  `conversation.started_at` to that conversation's first ASSISTANT
  message's `created_at`), across conversations in the period that have at
  least one assistant message. `None` if none do.
- **average_conversation_length_messages**: AVG(message count) across
  conversations in the period, all roles included (user, assistant, tool,
  system) — "length" here means turns exchanged, not duration.
- **conversation_completion_rate**: COUNT(conversations WHERE
  status=COMPLETED) / total_conversations in the period.
- **estimated_staff_time_saved_minutes**: genuine_widget_conversations *
  `Settings.estimated_staff_minutes_per_conversation` (default 5.0) — a
  single, global, configurable assumption about how many minutes of staff
  time one handled real-visitor conversation replaces. This has no
  per-tenant empirical basis; it is always returned and labeled as an
  **estimate**, never presented as measured fact, and never described as
  revenue.

## Test/preview exclusion

Every count-based metric above defaults to source ∈ {`widget`} only
(genuine visitor traffic) — `test` and `preview` conversations, and
anything derived from them, are excluded unless the caller passes
`include_test_preview=True`, in which case all three sources are included.
`genuine_widget_conversations` / `preview_conversations` /
`test_conversations` are always broken out individually regardless, so a
caller can see the excluded volume even in the default view.

## Tenant timezone and date bounds

`resolve_period` computes the requested preset ("today" / "7d" / "30d" /
"custom") as whole calendar days in the *tenant's* timezone, converts those
boundaries to UTC, and every query below filters/stores on the UTC
`started_at`/`created_at` columns using those UTC bounds — the database
never does timezone arithmetic itself. A custom range is capped at
`Settings.analytics_max_range_days` (366 by default) so a client cannot
request an unbounded, expensive scan.

## Revenue

Nothing in this module computes, infers, or displays a monetary amount.
`WON`/`LOST` enquiry statuses are operational labels only (see
app/services/enquiry_service.py) and never feed into any of the above.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select, true
from sqlalchemy.orm import Session, aliased

from app.config import Settings
from app.core.conversation_source import ConversationSource, source_case_expression
from app.models.appointment_request import AppointmentRequest
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.enquiry import Enquiry
from app.models.enums import (
    AppointmentRequestStatus,
    ConversationMessageRole,
    ConversationStatus,
    HandoffStatus,
)
from app.models.human_handoff import HumanHandoff
from app.models.widget_visitor_session import WidgetVisitorSession

VALID_PRESETS = ("today", "7d", "30d", "custom")


class InvalidAnalyticsRangeError(Exception):
    pass


@dataclass(frozen=True)
class AnalyticsPeriod:
    start_utc: datetime
    end_utc: datetime  # exclusive
    start_date: date
    end_date: date  # inclusive, in tenant timezone


def resolve_period(
    *,
    preset: str,
    tenant_timezone: str,
    custom_start: date | None,
    custom_end: date | None,
    max_range_days: int,
) -> AnalyticsPeriod:
    if preset not in VALID_PRESETS:
        raise InvalidAnalyticsRangeError(f"Unknown range preset '{preset}'.")
    try:
        tz = ZoneInfo(tenant_timezone)
    except ZoneInfoNotFoundError as exc:
        raise InvalidAnalyticsRangeError(f"'{tenant_timezone}' is not a recognized timezone.") from exc

    today = datetime.now(tz).date()
    if preset == "today":
        start_date, end_date = today, today
    elif preset == "7d":
        start_date, end_date = today - timedelta(days=6), today
    elif preset == "30d":
        start_date, end_date = today - timedelta(days=29), today
    else:
        if custom_start is None or custom_end is None:
            raise InvalidAnalyticsRangeError("custom_start and custom_end are required for a custom range.")
        start_date, end_date = custom_start, custom_end

    if end_date < start_date:
        raise InvalidAnalyticsRangeError("end date cannot be before start date.")
    if (end_date - start_date).days + 1 > max_range_days:
        raise InvalidAnalyticsRangeError(f"Date range cannot exceed {max_range_days} days.")

    start_utc = datetime.combine(start_date, time.min, tzinfo=tz).astimezone(UTC)
    end_utc = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
    return AnalyticsPeriod(start_utc=start_utc, end_utc=end_utc, start_date=start_date, end_date=end_date)


def _safe_rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _source_filter(source_expr, include_test_preview: bool):  # noqa: ANN001
    if include_test_preview:
        return true()
    return source_expr == ConversationSource.WIDGET.value


def get_overview(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    period: AnalyticsPeriod,
    receptionist_id: uuid.UUID | None,
    include_test_preview: bool,
    settings: Settings,
) -> dict:
    session_alias = aliased(WidgetVisitorSession)
    source_expr = source_case_expression(Conversation.mode, session_alias.is_platform_preview)

    conv_conditions = [
        Conversation.tenant_id == tenant_id,
        Conversation.started_at >= period.start_utc,
        Conversation.started_at < period.end_utc,
    ]
    if receptionist_id is not None:
        conv_conditions.append(Conversation.receptionist_id == receptionist_id)

    base_from = Conversation.__table__.outerjoin(session_alias, session_alias.conversation_id == Conversation.id)

    # --- Query 1: conversation-level counts (one row, conditional aggregates) ---
    conv_row = db.execute(
        select(
            func.count(Conversation.id).filter(_source_filter(source_expr, include_test_preview)),
            func.count(Conversation.id).filter(source_expr == ConversationSource.WIDGET.value),
            func.count(Conversation.id).filter(source_expr == ConversationSource.PREVIEW.value),
            func.count(Conversation.id).filter(source_expr == ConversationSource.TEST.value),
            func.count(Conversation.id).filter(
                _source_filter(source_expr, include_test_preview), Conversation.status == ConversationStatus.COMPLETED
            ),
            func.count(Conversation.id).filter(
                _source_filter(source_expr, include_test_preview), Conversation.had_safety_event.is_(True)
            ),
        )
        .select_from(base_from)
        .where(*conv_conditions)
    ).one()
    total_conversations, genuine_widget, preview, test, completed, safety_interventions = conv_row

    # --- Query 2: unique visitor sessions ---
    session_conditions = [*conv_conditions, session_alias.id.is_not(None)]
    if not include_test_preview:
        session_conditions.append(session_alias.is_platform_preview.is_(False))
    unique_sessions = (
        db.execute(select(func.count(session_alias.id)).select_from(base_from).where(*session_conditions)).scalar() or 0
    )

    # --- Query 3: contacts captured (joined for source classification) ---
    contact_conditions = [
        Contact.tenant_id == tenant_id,
        Contact.created_at >= period.start_utc,
        Contact.created_at < period.end_utc,
    ]
    contact_from = Contact.__table__.outerjoin(Conversation, Conversation.id == Contact.conversation_id).outerjoin(
        session_alias, session_alias.conversation_id == Conversation.id
    )
    if receptionist_id is not None:
        contact_conditions.append(Conversation.receptionist_id == receptionist_id)
    if include_test_preview:
        # NULL conversation_id (orphaned contact) is only included here.
        pass
    else:
        contact_conditions.append(source_expr == ConversationSource.WIDGET.value)
    contacts_captured = (
        db.execute(select(func.count(Contact.id)).select_from(contact_from).where(*contact_conditions)).scalar() or 0
    )

    # --- Query 4: enquiries ---
    enquiry_conditions = [
        Enquiry.tenant_id == tenant_id,
        Enquiry.created_at >= period.start_utc,
        Enquiry.created_at < period.end_utc,
    ]
    enquiry_from = Enquiry.__table__.join(Conversation, Conversation.id == Enquiry.conversation_id).outerjoin(
        session_alias, session_alias.conversation_id == Conversation.id
    )
    if receptionist_id is not None:
        enquiry_conditions.append(Enquiry.receptionist_id == receptionist_id)
    enquiry_conditions.append(_source_filter(source_expr, include_test_preview))
    enquiries_created, qualified_enquiries = db.execute(
        select(
            func.count(Enquiry.id),
            func.count(Enquiry.id).filter(Enquiry.qualification_complete.is_(True)),
        )
        .select_from(enquiry_from)
        .where(*enquiry_conditions)
    ).one()

    # --- Query 5: appointment requests ---
    appt_conditions = [
        AppointmentRequest.tenant_id == tenant_id,
        AppointmentRequest.created_at >= period.start_utc,
        AppointmentRequest.created_at < period.end_utc,
    ]
    appt_from = Conversation.__table__.join(
        AppointmentRequest, AppointmentRequest.conversation_id == Conversation.id
    ).outerjoin(session_alias, session_alias.conversation_id == Conversation.id)
    if receptionist_id is not None:
        appt_conditions.append(AppointmentRequest.receptionist_id == receptionist_id)
    appt_conditions.append(_source_filter(source_expr, include_test_preview))
    appointment_requests, pending_appointments, confirmed_appointments = db.execute(
        select(
            func.count(AppointmentRequest.id),
            func.count(AppointmentRequest.id).filter(AppointmentRequest.status == AppointmentRequestStatus.PENDING),
            func.count(AppointmentRequest.id).filter(AppointmentRequest.status == AppointmentRequestStatus.CONFIRMED),
        )
        .select_from(appt_from)
        .where(*appt_conditions)
    ).one()

    # --- Query 6: human handoffs ---
    handoff_conditions = [
        HumanHandoff.tenant_id == tenant_id,
        HumanHandoff.created_at >= period.start_utc,
        HumanHandoff.created_at < period.end_utc,
    ]
    handoff_from = Conversation.__table__.join(HumanHandoff, HumanHandoff.conversation_id == Conversation.id).outerjoin(
        session_alias, session_alias.conversation_id == Conversation.id
    )
    if receptionist_id is not None:
        handoff_conditions.append(HumanHandoff.receptionist_id == receptionist_id)
    handoff_conditions.append(_source_filter(source_expr, include_test_preview))
    human_handoffs, open_handoffs, resolved_handoffs = db.execute(
        select(
            func.count(HumanHandoff.id),
            func.count(HumanHandoff.id).filter(HumanHandoff.status == HandoffStatus.OPEN),
            func.count(HumanHandoff.id).filter(HumanHandoff.status == HandoffStatus.RESOLVED),
        )
        .select_from(handoff_from)
        .where(*handoff_conditions)
    ).one()

    # --- Query 7: fallback/unanswered messages ---
    fallback_from = ConversationMessage.__table__.join(
        Conversation, Conversation.id == ConversationMessage.conversation_id
    ).outerjoin(session_alias, session_alias.conversation_id == Conversation.id)
    fallback_conditions = [*conv_conditions, ConversationMessage.is_fallback_response.is_(True)]
    fallback_conditions.append(_source_filter(source_expr, include_test_preview))
    unanswered_or_fallback = (
        db.execute(
            select(func.count(ConversationMessage.id)).select_from(fallback_from).where(*fallback_conditions)
        ).scalar()
        or 0
    )

    # --- Query 8: average first-response time and conversation length ---
    per_conversation = (
        select(
            Conversation.id.label("conversation_id"),
            Conversation.started_at.label("started_at"),
            func.min(ConversationMessage.created_at)
            .filter(ConversationMessage.role == ConversationMessageRole.ASSISTANT)
            .label("first_assistant_at"),
            func.count(ConversationMessage.id).label("message_count"),
        )
        .select_from(
            Conversation.__table__.outerjoin(session_alias, session_alias.conversation_id == Conversation.id).outerjoin(
                ConversationMessage, ConversationMessage.conversation_id == Conversation.id
            )
        )
        .where(*conv_conditions, _source_filter(source_expr, include_test_preview))
        .group_by(Conversation.id, Conversation.started_at)
        .subquery()
    )
    response_time_seconds = func.extract("epoch", per_conversation.c.first_assistant_at - per_conversation.c.started_at)
    avg_first_response, avg_length = db.execute(
        select(
            func.avg(response_time_seconds).filter(per_conversation.c.first_assistant_at.is_not(None)),
            func.avg(per_conversation.c.message_count),
        )
    ).one()

    return {
        "period_start": period.start_date.isoformat(),
        "period_end": period.end_date.isoformat(),
        "receptionist_id": str(receptionist_id) if receptionist_id else None,
        "include_test_preview": include_test_preview,
        "total_conversations": total_conversations,
        "genuine_widget_conversations": genuine_widget,
        "preview_conversations": preview,
        "test_conversations": test,
        "unique_visitor_sessions": unique_sessions,
        "contacts_captured": contacts_captured,
        "contact_capture_rate": _safe_rate(contacts_captured, genuine_widget),
        "enquiries_created": enquiries_created,
        "qualified_enquiries": qualified_enquiries,
        "qualification_completion_rate": _safe_rate(qualified_enquiries, enquiries_created),
        "appointment_requests": appointment_requests,
        "pending_appointments": pending_appointments,
        "confirmed_appointments": confirmed_appointments,
        "human_handoffs": human_handoffs,
        "open_handoffs": open_handoffs,
        "resolved_handoffs": resolved_handoffs,
        "unanswered_or_fallback_responses": unanswered_or_fallback,
        "safety_interventions": safety_interventions,
        "average_first_response_time_seconds": float(avg_first_response) if avg_first_response is not None else None,
        "average_conversation_length_messages": float(avg_length) if avg_length is not None else None,
        "conversation_completion_rate": _safe_rate(completed, total_conversations),
        "estimated_staff_time_saved_minutes": genuine_widget * settings.estimated_staff_minutes_per_conversation,
        "estimated_staff_time_saved_minutes_is_estimate": True,
    }


def get_timeseries(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    period: AnalyticsPeriod,
    tenant_timezone: str,
    receptionist_id: uuid.UUID | None,
    include_test_preview: bool,
) -> list[dict]:
    """One row per calendar day (tenant timezone) in the period, each with
    its own conversation/enquiry/appointment/handoff counts — the same
    filters as get_overview, bucketed by day for a chart. Still a single
    query per series (three total), never one query per day."""
    session_alias = aliased(WidgetVisitorSession)
    source_expr = source_case_expression(Conversation.mode, session_alias.is_platform_preview)
    base_from = Conversation.__table__.outerjoin(session_alias, session_alias.conversation_id == Conversation.id)

    conv_conditions = [
        Conversation.tenant_id == tenant_id,
        Conversation.started_at >= period.start_utc,
        Conversation.started_at < period.end_utc,
        _source_filter(source_expr, include_test_preview),
    ]
    if receptionist_id is not None:
        conv_conditions.append(Conversation.receptionist_id == receptionist_id)

    day_bucket = func.date(func.timezone(tenant_timezone, Conversation.started_at))
    conv_rows = db.execute(
        select(day_bucket.label("day"), func.count(Conversation.id))
        .select_from(base_from)
        .where(*conv_conditions)
        .group_by("day")
    ).all()
    conv_by_day = {row.day: row[1] for row in conv_rows}

    appt_from = Conversation.__table__.join(
        AppointmentRequest, AppointmentRequest.conversation_id == Conversation.id
    ).outerjoin(session_alias, session_alias.conversation_id == Conversation.id)
    appt_conditions = [
        AppointmentRequest.tenant_id == tenant_id,
        AppointmentRequest.created_at >= period.start_utc,
        AppointmentRequest.created_at < period.end_utc,
        _source_filter(source_expr, include_test_preview),
    ]
    if receptionist_id is not None:
        appt_conditions.append(AppointmentRequest.receptionist_id == receptionist_id)
    appt_day_bucket = func.date(func.timezone(tenant_timezone, AppointmentRequest.created_at))
    appt_rows = db.execute(
        select(appt_day_bucket.label("day"), func.count(AppointmentRequest.id))
        .select_from(appt_from)
        .where(*appt_conditions)
        .group_by("day")
    ).all()
    appt_by_day = {row.day: row[1] for row in appt_rows}

    handoff_from = Conversation.__table__.join(HumanHandoff, HumanHandoff.conversation_id == Conversation.id).outerjoin(
        session_alias, session_alias.conversation_id == Conversation.id
    )
    handoff_conditions = [
        HumanHandoff.tenant_id == tenant_id,
        HumanHandoff.created_at >= period.start_utc,
        HumanHandoff.created_at < period.end_utc,
        _source_filter(source_expr, include_test_preview),
    ]
    if receptionist_id is not None:
        handoff_conditions.append(HumanHandoff.receptionist_id == receptionist_id)
    handoff_day_bucket = func.date(func.timezone(tenant_timezone, HumanHandoff.created_at))
    handoff_rows = db.execute(
        select(handoff_day_bucket.label("day"), func.count(HumanHandoff.id))
        .select_from(handoff_from)
        .where(*handoff_conditions)
        .group_by("day")
    ).all()
    handoff_by_day = {row.day: row[1] for row in handoff_rows}

    series = []
    current = period.start_date
    while current <= period.end_date:
        series.append(
            {
                "date": current.isoformat(),
                "conversations": conv_by_day.get(current, 0),
                "appointment_requests": appt_by_day.get(current, 0),
                "human_handoffs": handoff_by_day.get(current, 0),
            }
        )
        current += timedelta(days=1)
    return series
