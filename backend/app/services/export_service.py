"""Owner/admin-only CSV exports (enforced by the route dependency, not
here). Every export is tenant-scoped, date-range-bounded, and capped at
app.core.csv_export.MAX_EXPORT_ROWS — generated entirely in memory (see
build_csv) and never written to a persistent file on the server. The
caller (app/api/v1/exports.py) is responsible for recording an
ActivityEvent for the export action; this module only builds the CSV
bytes.

Each export additionally accepts the same "safe" filters its corresponding
dashboard list page supports (status for enquiries/appointments/handoffs;
source for conversations) — never search or receptionist_id, since those
narrow to a specific record rather than a class of records and add no
export-specific value over just looking at the list. An invalid filter
value raises InvalidExportFilterError, mapped to a 422 by the route.

Conversations export is *metadata only* by default — no message content,
no citations, no tool payloads. Every column below is already visible
elsewhere in the dashboard to the same owner/admin audience; nothing here
introduces a new disclosure."""

import uuid
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.core.conversation_source import ConversationSource
from app.core.csv_export import MAX_EXPORT_ROWS, build_csv
from app.models.enums import AppointmentRequestStatus, EnquiryStatus, HandoffStatus
from app.repositories.appointment_request import AppointmentRequestFilters, AppointmentRequestRepository
from app.repositories.contact import ContactRepository
from app.repositories.conversation import ConversationFilters, ConversationRepository
from app.repositories.enquiry import EnquiryFilters, EnquiryRepository
from app.repositories.human_handoff import HandoffFilters, HumanHandoffRepository


class InvalidExportFilterError(Exception):
    pass


def _parse_enum_list(values: list[str] | None, enum_cls: type) -> tuple | None:
    if not values:
        return None
    try:
        return tuple(enum_cls(v) for v in values)
    except ValueError as exc:
        raise InvalidExportFilterError(f"'{exc.args[0]}' is not a valid value for {enum_cls.__name__}.") from exc


def export_conversations_csv(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    created_after: datetime,
    created_before: datetime,
    sources: list[str] | None = None,
) -> str:
    sources_tuple = None
    if sources:
        try:
            sources_tuple = tuple(ConversationSource(s) for s in sources)
        except ValueError as exc:
            raise InvalidExportFilterError(f"'{exc.args[0]}' is not a valid conversation source.") from exc

    repo = ConversationRepository(db, tenant_id)
    rows, _ = repo.list_dashboard(
        filters=ConversationFilters(started_after=created_after, started_before=created_before, sources=sources_tuple),
        sort_column="started_at",
        sort_descending=True,
        limit=MAX_EXPORT_ROWS + 1,
        offset=0,
    )
    header = [
        "id",
        "started_at",
        "source",
        "status",
        "receptionist_id",
        "message_count_unavailable",
        "qualification_complete",
        "had_safety_event",
    ]
    return build_csv(
        header=header,
        rows=(
            [
                conv.id,
                conv.started_at.isoformat(),
                source.value,
                conv.status.value,
                conv.receptionist_id,
                "see conversation detail",
                conv.qualification_complete,
                conv.had_safety_event,
            ]
            for conv, source in rows
        ),
    )


def export_contacts_csv(db: Session, *, tenant_id: uuid.UUID, created_after: datetime, created_before: datetime) -> str:
    # No status/source concept applies to contacts — no additional filter.
    repo = ContactRepository(db, tenant_id)
    rows, _ = repo.list_dashboard(
        created_after=created_after,
        created_before=created_before,
        search=None,
        sort_descending=True,
        limit=MAX_EXPORT_ROWS + 1,
        offset=0,
    )
    header = ["id", "created_at", "name", "email", "phone", "preferred_contact_method", "marketing_consent", "source"]
    return build_csv(
        header=header,
        rows=(
            [
                c.id,
                c.created_at.isoformat(),
                c.name,
                c.normalized_email,
                c.normalized_phone,
                c.preferred_contact_method.value if c.preferred_contact_method else None,
                c.marketing_consent,
                c.source,
            ]
            for c in rows
        ),
    )


def export_enquiries_csv(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    created_after: datetime,
    created_before: datetime,
    statuses: list[str] | None = None,
) -> str:
    statuses_tuple = _parse_enum_list(statuses, EnquiryStatus)
    repo = EnquiryRepository(db, tenant_id)
    rows, _ = repo.list_dashboard(
        filters=EnquiryFilters(created_after=created_after, created_before=created_before, statuses=statuses_tuple),
        sort_column="created_at",
        sort_descending=True,
        limit=MAX_EXPORT_ROWS + 1,
        offset=0,
    )
    header = [
        "id",
        "created_at",
        "status",
        "receptionist_id",
        "contact_id",
        "qualification_complete",
        "recommended_next_action",
    ]
    return build_csv(
        header=header,
        rows=(
            [
                e.id,
                e.created_at.isoformat(),
                e.status.value,
                e.receptionist_id,
                e.contact_id,
                e.qualification_complete,
                e.recommended_next_action,
            ]
            for e in rows
        ),
    )


def export_appointments_csv(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    requested_date_after: date,
    requested_date_before: date,
    statuses: list[str] | None = None,
) -> str:
    """Deliberately filters by `requested_date` (the appointment's own
    date), not `created_at` — matching exactly what the appointments list
    page's own date-range filter means (see
    app/api/v1/dashboard_records.py::list_appointments), so a tenant
    exporting "this month's appointments" gets the same rows the list page
    showed them, not a different date field silently substituted."""
    statuses_tuple = _parse_enum_list(statuses, AppointmentRequestStatus)
    repo = AppointmentRequestRepository(db, tenant_id)
    rows, _ = repo.list_dashboard(
        filters=AppointmentRequestFilters(
            requested_date_after=requested_date_after,
            requested_date_before=requested_date_before,
            statuses=statuses_tuple,
        ),
        sort_column="requested_date",
        sort_descending=True,
        limit=MAX_EXPORT_ROWS + 1,
        offset=0,
    )
    header = [
        "id",
        "created_at",
        "status",
        "requested_date",
        "requested_time_window",
        "timezone",
        "location_id",
        "service_id",
        "contact_id",
    ]
    return build_csv(
        header=header,
        rows=(
            [
                a.id,
                a.created_at.isoformat(),
                a.status.value,
                a.requested_date.isoformat(),
                a.requested_time_window,
                a.timezone,
                a.location_id,
                a.service_id,
                a.contact_id,
            ]
            for a in rows
        ),
    )


def export_handoffs_csv(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    created_after: datetime,
    created_before: datetime,
    statuses: list[str] | None = None,
) -> str:
    statuses_tuple = _parse_enum_list(statuses, HandoffStatus)
    repo = HumanHandoffRepository(db, tenant_id)
    rows, _ = repo.list_dashboard(
        filters=HandoffFilters(created_after=created_after, created_before=created_before, statuses=statuses_tuple),
        sort_column="created_at",
        sort_descending=True,
        limit=MAX_EXPORT_ROWS + 1,
        offset=0,
    )
    header = [
        "id",
        "created_at",
        "status",
        "urgency",
        "preferred_contact_method",
        "assigned_user_id",
        "contact_id",
        "resolved_at",
    ]
    return build_csv(
        header=header,
        rows=(
            [
                h.id,
                h.created_at.isoformat(),
                h.status.value,
                h.urgency,
                h.preferred_contact_method.value if h.preferred_contact_method else None,
                h.assigned_user_id,
                h.contact_id,
                h.resolved_at.isoformat() if h.resolved_at else None,
            ]
            for h in rows
        ),
    )
