"""Contact capture for the public widget. Two things are kept structurally
separate on purpose:

1. Providing name/email/phone so the business can reply to a direct
   enquiry (the normal, expected act of using a contact form).
2. `marketing_consent` — an explicit, separate, unticked-by-default opt-in
   that must never be inferred from (1). A visitor who gives contact
   details to get an appointment or a callback has not thereby agreed to
   receive marketing; only a distinct, explicit `True` on this field does,
   and only that sets `consent_captured_at`.

Dedup is tenant-scoped and best-effort: matching by normalized email first,
then normalized phone. A match updates the existing row rather than
creating a duplicate contact per conversation. This is never used to merge
across tenants, and a public response never reveals whether a match
occurred (see app/api/v1/widget_public.py).

Reviewed explicitly for the failure mode "an unauthenticated visitor who
submits an existing email or phone number overwrites trusted contact
information arbitrarily" (see tests/test_contact_service.py):

- `name`/`normalized_email`/`normalized_phone` are only ever filled in when
  the *existing* value is empty (`if X and not existing.X`) — a later
  submission with a *conflicting* name/email/phone for an already-populated
  field is silently ignored, never overwritten. Enrichment of a still-empty
  field from a match found via a *different* field (e.g. adding a phone
  number to a contact matched by email) is intentionally permitted — the
  fields are visitor-submitted either way, and a tenant reviewing the
  record can judge new information the same way they would judge the
  original submission.
- `marketing_consent` only ever moves False → True here, never the
  reverse — a later submission with the checkbox left unticked (`False`)
  cannot erase a previously recorded explicit `True`.
- `preferred_contact_method` is the one field that *is* freely overwritten
  on a match — deliberately: it is a live "how to reach me" preference a
  visitor may legitimately update, not an identity fact.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.normalization import normalize_email, normalize_phone
from app.models.contact import Contact
from app.models.enums import PreferredContactMethod
from app.repositories.contact import ContactRepository


def capture_contact(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    name: str | None,
    email: str | None,
    phone: str | None,
    preferred_contact_method: PreferredContactMethod | None,
    marketing_consent: bool,
    source: str = "widget",
) -> Contact:
    repo = ContactRepository(db, tenant_id)

    normalized_email = normalize_email(email) if email else None
    normalized_phone = normalize_phone(phone) if phone else None

    existing = None
    if normalized_email:
        existing = repo.get_by_normalized_email(normalized_email)
    if existing is None and normalized_phone:
        existing = repo.get_by_normalized_phone(normalized_phone)

    if existing is not None:
        if name and not existing.name:
            existing.name = name
        if normalized_email and not existing.normalized_email:
            existing.normalized_email = normalized_email
        if normalized_phone and not existing.normalized_phone:
            existing.normalized_phone = normalized_phone
        if preferred_contact_method is not None:
            existing.preferred_contact_method = preferred_contact_method
        if marketing_consent and not existing.marketing_consent:
            existing.marketing_consent = True
            existing.consent_captured_at = datetime.now(UTC)
        if conversation_id is not None:
            existing.conversation_id = conversation_id
        return existing

    contact = Contact(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        name=name,
        normalized_email=normalized_email,
        normalized_phone=normalized_phone,
        preferred_contact_method=preferred_contact_method,
        marketing_consent=marketing_consent,
        consent_captured_at=datetime.now(UTC) if marketing_consent else None,
        source=source,
    )
    repo.add(contact)
    db.flush()
    return contact
