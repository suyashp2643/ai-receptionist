"""Public marketing-site lead capture (Phase 7). See app/models/public_lead.py
for why this is a global, not tenant-owned, model, and docs/security.md for
the full threat model (honeypot, rate limiting, no public read endpoint)."""

from sqlalchemy.orm import Session

from app.core.normalization import normalize_email
from app.models.public_lead import PublicLead
from app.schemas.public_lead import PublicLeadCreateRequest


def create_lead(db: Session, *, payload: PublicLeadCreateRequest, ip_hash: str | None) -> PublicLead | None:
    """Returns the persisted lead, or None if this was a honeypot hit — the
    caller must respond identically either way (see
    PublicLeadSubmitResponse's docstring)."""
    if payload.hp_field:
        return None

    lead = PublicLead(
        full_name=payload.full_name,
        work_email=payload.work_email,
        normalized_email=normalize_email(payload.work_email),
        company=payload.company,
        website=payload.website,
        country=payload.country,
        industry=payload.industry,
        company_size=payload.company_size,
        estimated_monthly_volume=payload.estimated_monthly_volume,
        primary_use_case=payload.primary_use_case,
        message=payload.message,
        contact_consent=payload.contact_consent,
        marketing_consent=payload.marketing_consent,
        submitted_ip_hash=ip_hash,
    )
    db.add(lead)
    db.flush()
    return lead
