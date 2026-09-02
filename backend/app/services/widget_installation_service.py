import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import Settings
from app.core.domain_validation import InvalidDomainError, is_localhost, normalize_domain
from app.models.enums import WidgetInstallationStatus
from app.models.widget_installation import WidgetInstallation
from app.repositories.receptionist import ReceptionistRepository
from app.repositories.widget_installation import WidgetInstallationRepository
from app.schemas.widget_installation import MAX_ALLOWED_DOMAINS, WidgetInstallationCreate, WidgetInstallationUpdate


class ReceptionistNotFoundError(ValueError):
    """Raised when a WidgetInstallation is created/updated against a
    receptionist_id that does not belong to this tenant — the composite FK
    (tenant_id, receptionist_id) would also reject this at flush time, but
    checking explicitly here lets the API return a clean 404 instead of a
    raw IntegrityError."""


def normalize_allowed_domains(domains: list[str], *, settings: Settings) -> list[str]:
    """Shared by create/update so both paths apply the identical rule set:
    valid hostname syntax, no wildcards, localhost gated to development."""
    if len(domains) > MAX_ALLOWED_DOMAINS:
        raise ValueError(f"At most {MAX_ALLOWED_DOMAINS} allowed domains may be configured.")

    allow_localhost = settings.environment == "development"
    normalized: list[str] = []
    for raw in domains:
        try:
            domain = normalize_domain(raw)
        except InvalidDomainError as exc:
            raise ValueError(str(exc)) from exc
        if is_localhost(domain) and not allow_localhost:
            raise ValueError("Localhost domains are only permitted in a development environment.")
        if domain not in normalized:
            normalized.append(domain)
    return normalized


def create_installation(
    db: Session, *, tenant_id: uuid.UUID, settings: Settings, payload: WidgetInstallationCreate
) -> WidgetInstallation:
    receptionist = ReceptionistRepository(db, tenant_id).get(payload.receptionist_id)
    if receptionist is None:
        raise ReceptionistNotFoundError(f"Receptionist {payload.receptionist_id} not found for this tenant.")

    installation = WidgetInstallation(
        tenant_id=tenant_id,
        receptionist_id=payload.receptionist_id,
        allowed_domains=normalize_allowed_domains(payload.allowed_domains, settings=settings),
        launcher_position=payload.launcher_position,
        privacy_notice=payload.privacy_notice,
    )
    if payload.ai_disclosure is not None:
        installation.ai_disclosure = payload.ai_disclosure
    WidgetInstallationRepository(db, tenant_id).add(installation)
    db.flush()
    return installation


def update_installation(
    db: Session,
    *,
    settings: Settings,
    installation: WidgetInstallation,
    payload: WidgetInstallationUpdate,
) -> WidgetInstallation:
    data = payload.model_dump(exclude_unset=True)
    if "allowed_domains" in data and data["allowed_domains"] is not None:
        data["allowed_domains"] = normalize_allowed_domains(data["allowed_domains"], settings=settings)
    for field, value in data.items():
        setattr(installation, field, value)
    return installation


def activate_installation(installation: WidgetInstallation) -> WidgetInstallation:
    installation.status = WidgetInstallationStatus.ACTIVE
    installation.revoked_at = None
    return installation


def pause_installation(installation: WidgetInstallation) -> WidgetInstallation:
    installation.status = WidgetInstallationStatus.PAUSED
    return installation


def revoke_installation(installation: WidgetInstallation) -> WidgetInstallation:
    """Revocation is terminal: a revoked installation's public_id must never
    be reactivated (see WidgetInstallation docstring) — a tenant that wants
    the widget back creates a new installation instead, which mints a new
    public_id and requires re-embedding the snippet. This is deliberate:
    the old public_id may already be cached/scraped from a page's source."""
    installation.status = WidgetInstallationStatus.REVOKED
    installation.revoked_at = datetime.now(UTC)
    return installation
