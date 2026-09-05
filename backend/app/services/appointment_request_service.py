"""Appointment REQUEST creation for the public widget. Phase 5 has no live
calendar — every request is created with status=PENDING and must never be
represented to a visitor as confirmed (see AppointmentRequest's docstring
and app/schemas/widget_public.py's response wording)."""

import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.timezones import VALID_TIMEZONES, normalize_timezone
from app.integrations import payload_builders
from app.integrations.envelope import EventType
from app.models.appointment_request import AppointmentRequest
from app.models.business_location import BusinessLocation
from app.models.contact import Contact
from app.models.enums import AppointmentRequestStatus
from app.repositories.appointment_request import AppointmentRequestRepository
from app.repositories.business_location import BusinessLocationRepository
from app.repositories.service import ServiceRepository
from app.services import activity_service, outbox_producer_service
from app.services.concurrency import apply_versioned_update

# Owner/admin-only workflow (see app/api/deps.py's require_tenant_role usage
# in app/api/v1/dashboard_records.py) — never automatically transitioned,
# and never notifies the visitor (Phase 6 has no delivery mechanism; see
# docs/security.md).
APPOINTMENT_STATUS_TRANSITIONS: dict[AppointmentRequestStatus, frozenset[AppointmentRequestStatus]] = {
    AppointmentRequestStatus.PENDING: frozenset(
        {AppointmentRequestStatus.CONFIRMED, AppointmentRequestStatus.DECLINED, AppointmentRequestStatus.CANCELLED}
    ),
    AppointmentRequestStatus.CONFIRMED: frozenset({AppointmentRequestStatus.CANCELLED}),
    AppointmentRequestStatus.DECLINED: frozenset(),
    AppointmentRequestStatus.CANCELLED: frozenset(),
}


class InvalidAppointmentStatusTransitionError(Exception):
    pass


MAX_PAST_DAYS_ALLOWED = 0  # "today" in the governing timezone is the earliest acceptable date
MAX_FUTURE_DAYS_ALLOWED = 365


class InvalidAppointmentRequestError(ValueError):
    pass


def _today_in(tz_name: str) -> date:
    """The date boundary is computed deterministically from a real IANA
    timezone's wall clock — never UTC-as-a-proxy-for-local, and never the
    visitor's browser clock, which the server cannot trust."""
    return datetime.now(ZoneInfo(tz_name)).date()


def _validate_requested_date(requested_date: date, *, governing_timezone: str) -> None:
    today = _today_in(governing_timezone)
    earliest = today - timedelta(days=MAX_PAST_DAYS_ALLOWED)
    latest = today + timedelta(days=MAX_FUTURE_DAYS_ALLOWED)
    if requested_date < earliest:
        raise InvalidAppointmentRequestError("Requested date cannot be in the past.")
    if requested_date > latest:
        raise InvalidAppointmentRequestError(
            f"Requested date is too far in the future (max {MAX_FUTURE_DAYS_ALLOWED} days)."
        )


def _resolve_location(db: Session, *, tenant_id: uuid.UUID, location_id: uuid.UUID | None) -> BusinessLocation | None:
    if location_id is None:
        return None
    location = BusinessLocationRepository(db, tenant_id).get_active(location_id)
    if location is None:
        raise InvalidAppointmentRequestError("The selected location was not found for this business.")
    return location


def create_appointment_request(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    receptionist_id: uuid.UUID,
    conversation_id: uuid.UUID,
    contact_id: uuid.UUID | None,
    location_id: uuid.UUID | None,
    service_id: uuid.UUID | None,
    requested_date: date,
    requested_time: time | None,
    requested_time_window: str | None,
    timezone: str,
    notes: str | None,
    idempotency_key: str | None,
) -> AppointmentRequest:
    repo = AppointmentRequestRepository(db, tenant_id)

    if idempotency_key:
        existing = repo.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing

    # The submitted timezone is always validated, even when a location is
    # also selected: it is still stored on the row and shown back to the
    # tenant, so an invalid value must never reach the database silently.
    # Normalized first: a visitor's browser (via Intl.DateTimeFormat) can
    # report a legacy IANA alias — e.g. "Asia/Calcutta" — that this
    # backend's tzdata build doesn't recognize even though it's a real,
    # unambiguous timezone under its canonical name. See
    # app/core/timezones.py's LEGACY_TIMEZONE_ALIASES for why this is
    # necessary only here and not the dashboard's own timezone dropdown.
    timezone = normalize_timezone(timezone)
    if timezone not in VALID_TIMEZONES:
        raise InvalidAppointmentRequestError(f"'{timezone}' is not a recognized timezone.")

    service = None
    if service_id is not None:
        service = ServiceRepository(db, tenant_id).get_active(service_id)
        if service is None:
            raise InvalidAppointmentRequestError("The selected service was not found for this business.")

    location = _resolve_location(db, tenant_id=tenant_id, location_id=location_id)

    # A service restricted to one location must be requested either with no
    # location specified (auto-filled below) or with that exact location —
    # never a different one. This is the one place a client-supplied pair of
    # otherwise-independently-valid IDs could still describe an impossible
    # combination, so it is checked explicitly rather than left implicit.
    if service is not None and service.location_id is not None:
        if location is not None and location.id != service.location_id:
            raise InvalidAppointmentRequestError("The selected service is not offered at the selected location.")
        if location is None:
            location = _resolve_location(db, tenant_id=tenant_id, location_id=service.location_id)
            location_id = service.location_id

    governing_timezone = location.timezone if location is not None else timezone
    _validate_requested_date(requested_date, governing_timezone=governing_timezone)

    appointment_request = AppointmentRequest(
        tenant_id=tenant_id,
        receptionist_id=receptionist_id,
        conversation_id=conversation_id,
        contact_id=contact_id,
        location_id=location_id,
        service_id=service_id,
        requested_date=requested_date,
        requested_time=requested_time,
        requested_time_window=requested_time_window,
        timezone=timezone,
        notes=notes,
        idempotency_key=idempotency_key,
    )
    repo.add(appointment_request)
    db.flush()
    contact = db.get(Contact, contact_id) if contact_id else None
    outbox_producer_service.produce_event(
        db,
        tenant_id=tenant_id,
        event_type=EventType.APPOINTMENT_REQUEST_CREATED,
        payload=payload_builders.appointment_request_created(appointment_request, contact=contact),
        dedup_key=f"appointment_request.created:{appointment_request.id}",
        correlation_id=conversation_id,
    )
    return appointment_request


def update_status(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    appointment_request: AppointmentRequest,
    new_status: AppointmentRequestStatus,
    expected_version: int,
) -> AppointmentRequest:
    """Owner/admin-only (enforced by the caller's route dependency, not
    here). Never sends any notification to the visitor — Phase 6 has no
    delivery mechanism at all; the dashboard UI must say so explicitly.
    Raises InvalidAppointmentStatusTransitionError (422) or
    VersionConflictError (409)."""
    current = appointment_request.status
    if new_status == current:
        raise InvalidAppointmentStatusTransitionError(f"Appointment request is already '{current.value}'.")
    allowed = APPOINTMENT_STATUS_TRANSITIONS.get(current, frozenset())
    if new_status not in allowed:
        raise InvalidAppointmentStatusTransitionError(
            f"Cannot move an appointment request from '{current.value}' to '{new_status.value}'."
        )

    apply_versioned_update(
        db,
        appointment_request,
        expected_version=expected_version,
        values={"status": new_status},
    )
    activity_service.record(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action_type="appointment_request.status_changed",
        entity_type="appointment_request",
        entity_id=appointment_request.id,
        metadata={"from": current.value, "to": new_status.value},
    )
    outbox_producer_service.produce_event(
        db,
        tenant_id=tenant_id,
        event_type=EventType.APPOINTMENT_REQUEST_STATUS_CHANGED,
        payload=payload_builders.appointment_request_status_changed(appointment_request, previous_status=current.value),
        dedup_key=f"appointment_request.status_changed:{appointment_request.id}:{appointment_request.version}",
    )
    db.flush()
    return appointment_request
