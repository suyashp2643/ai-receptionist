import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_db, get_tenant_context, require_tenant_role
from app.config import Settings, get_settings
from app.models.enums import TenantMemberRole, WidgetInstallationStatus
from app.models.widget_installation import WidgetInstallation
from app.repositories.widget_installation import WidgetInstallationRepository
from app.schemas.widget_installation import (
    WidgetInstallationCreate,
    WidgetInstallationRead,
    WidgetInstallationUpdate,
)
from app.services import widget_installation_service
from app.services.widget_installation_service import ReceptionistNotFoundError

router = APIRouter()


class WidgetEmbedSnippetRead(WidgetInstallationRead):
    embed_snippet: str
    widget_bundle_url: str


def _build_snippet(*, bundle_url: str, public_id: str) -> str:
    return (
        f'<script\n'
        f'  src="{bundle_url}"\n'
        f'  data-receptionist-id="{public_id}"\n'
        f"  async\n"
        f"></script>"
    )


def _get_installation_or_404(installation_id: uuid.UUID, ctx: TenantContext, db: Session) -> WidgetInstallation:
    installation = WidgetInstallationRepository(db, ctx.tenant_id).get(installation_id)
    if installation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Widget installation not found")
    return installation


@router.get("/tenants/{tenant_id}/widget-installations", response_model=list[WidgetInstallationRead])
def list_widget_installations(
    ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)
) -> list[WidgetInstallationRead]:
    installations = WidgetInstallationRepository(db, ctx.tenant_id).list()
    return [WidgetInstallationRead.model_validate(i) for i in installations]


@router.post(
    "/tenants/{tenant_id}/widget-installations",
    response_model=WidgetInstallationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_widget_installation(
    payload: WidgetInstallationCreate,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> WidgetInstallationRead:
    try:
        installation = widget_installation_service.create_installation(
            db, tenant_id=ctx.tenant_id, settings=settings, payload=payload
        )
    except ReceptionistNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return WidgetInstallationRead.model_validate(installation)


@router.get("/tenants/{tenant_id}/widget-installations/{installation_id}", response_model=WidgetInstallationRead)
def get_widget_installation(
    installation_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> WidgetInstallationRead:
    installation = _get_installation_or_404(installation_id, ctx, db)
    return WidgetInstallationRead.model_validate(installation)


@router.get(
    "/tenants/{tenant_id}/widget-installations/{installation_id}/embed-snippet",
    response_model=WidgetEmbedSnippetRead,
)
def get_widget_embed_snippet(
    installation_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> WidgetEmbedSnippetRead:
    installation = _get_installation_or_404(installation_id, ctx, db)
    snippet = _build_snippet(bundle_url=settings.widget_bundle_url, public_id=installation.public_id)
    return WidgetEmbedSnippetRead(
        **WidgetInstallationRead.model_validate(installation).model_dump(),
        embed_snippet=snippet,
        widget_bundle_url=settings.widget_bundle_url,
    )


@router.patch("/tenants/{tenant_id}/widget-installations/{installation_id}", response_model=WidgetInstallationRead)
def update_widget_installation(
    installation_id: uuid.UUID,
    payload: WidgetInstallationUpdate,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> WidgetInstallationRead:
    installation = _get_installation_or_404(installation_id, ctx, db)
    try:
        widget_installation_service.update_installation(
            db, settings=settings, installation=installation, payload=payload
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return WidgetInstallationRead.model_validate(installation)


def _require_not_revoked(installation: WidgetInstallation) -> None:
    if installation.status == WidgetInstallationStatus.REVOKED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This widget installation has been revoked and cannot be reactivated. "
                "Create a new installation instead."
            ),
        )


@router.post(
    "/tenants/{tenant_id}/widget-installations/{installation_id}/activate", response_model=WidgetInstallationRead
)
def activate_widget_installation(
    installation_id: uuid.UUID,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> WidgetInstallationRead:
    installation = _get_installation_or_404(installation_id, ctx, db)
    _require_not_revoked(installation)
    widget_installation_service.activate_installation(installation)
    return WidgetInstallationRead.model_validate(installation)


@router.post(
    "/tenants/{tenant_id}/widget-installations/{installation_id}/pause", response_model=WidgetInstallationRead
)
def pause_widget_installation(
    installation_id: uuid.UUID,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> WidgetInstallationRead:
    installation = _get_installation_or_404(installation_id, ctx, db)
    _require_not_revoked(installation)
    widget_installation_service.pause_installation(installation)
    return WidgetInstallationRead.model_validate(installation)


@router.post(
    "/tenants/{tenant_id}/widget-installations/{installation_id}/revoke", response_model=WidgetInstallationRead
)
def revoke_widget_installation(
    installation_id: uuid.UUID,
    ctx: TenantContext = Depends(require_tenant_role(TenantMemberRole.ADMIN)),
    db: Session = Depends(get_db),
) -> WidgetInstallationRead:
    installation = _get_installation_or_404(installation_id, ctx, db)
    widget_installation_service.revoke_installation(installation)
    return WidgetInstallationRead.model_validate(installation)
