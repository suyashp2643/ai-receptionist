from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.cookies import clear_auth_cookies, set_auth_cookies
from app.api.deps import get_current_user, get_db
from app.config import Settings, get_settings
from app.core.csrf import verify_csrf
from app.core.normalization import normalize_email
from app.models.user import User
from app.repositories.tenant_member import TenantMemberRepository
from app.schemas.auth import LoginRequest, MeResponse, RegisterRequest, TokenResponse
from app.schemas.tenant import TenantMembershipSummary
from app.schemas.user import UserPublic
from app.services import auth_service

router = APIRouter()


def _memberships_for(db: Session, user_id) -> list[TenantMembershipSummary]:
    rows = TenantMemberRepository(db).list_with_tenant_for_user(user_id)
    return [
        TenantMembershipSummary(
            tenant_id=tenant.id,
            tenant_name=tenant.name,
            tenant_slug=tenant.slug,
            role=member.role,
            status=member.status,
        )
        for member, tenant in rows
    ]


@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    try:
        user, _tenant, _member, session = auth_service.register_user(db, settings, payload)
    except auth_service.EmailAlreadyRegisteredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered.") from exc

    set_auth_cookies(
        response,
        settings,
        refresh_token=session.raw_refresh_token,
        refresh_max_age_seconds=settings.refresh_token_ttl_days * 24 * 3600,
    )

    return TokenResponse(
        access_token=session.access_token,
        expires_in=session.expires_in,
        user=UserPublic.model_validate(user),
        memberships=_memberships_for(db, user.id),
    )


@router.post("/auth/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    try:
        user, session = auth_service.login_user(
            db, settings, normalized_email=normalize_email(payload.email), password=payload.password
        )
    except auth_service.InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.") from exc

    set_auth_cookies(
        response,
        settings,
        refresh_token=session.raw_refresh_token,
        refresh_max_age_seconds=settings.refresh_token_ttl_days * 24 * 3600,
    )

    return TokenResponse(
        access_token=session.access_token,
        expires_in=session.expires_in,
        user=UserPublic.model_validate(user),
        memberships=_memberships_for(db, user.id),
    )


@router.post("/auth/refresh", response_model=TokenResponse, dependencies=[Depends(verify_csrf)])
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse | JSONResponse:
    def _unauthenticated_and_cleared() -> JSONResponse:
        # A plain HTTPException here would NOT work: when a route raises,
        # FastAPI's exception handler builds a brand-new Response and the
        # `response` object injected into this function (and anything set on
        # it, like cleared cookies) is discarded entirely. Returning our own
        # JSONResponse is the only way to both clear cookies AND signal 401
        # from this error path.
        error_response = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": {"message": "Not authenticated.", "status_code": 401}},
        )
        clear_auth_cookies(error_response, settings)
        return error_response

    raw_refresh_token = request.cookies.get(settings.refresh_cookie_name)
    if not raw_refresh_token:
        return _unauthenticated_and_cleared()

    try:
        user, session = auth_service.refresh_session(db, settings, raw_refresh_token=raw_refresh_token)
    except (auth_service.RefreshTokenInvalidError, auth_service.RefreshTokenReuseDetectedError):
        return _unauthenticated_and_cleared()

    set_auth_cookies(
        response,
        settings,
        refresh_token=session.raw_refresh_token,
        refresh_max_age_seconds=settings.refresh_token_ttl_days * 24 * 3600,
        existing_csrf_token=request.cookies.get(settings.csrf_cookie_name),
    )

    return TokenResponse(
        access_token=session.access_token,
        expires_in=session.expires_in,
        user=UserPublic.model_validate(user),
        memberships=_memberships_for(db, user.id),
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(verify_csrf)])
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    raw_refresh_token = request.cookies.get(settings.refresh_cookie_name)
    auth_service.logout_session(db, raw_refresh_token=raw_refresh_token)
    clear_auth_cookies(response, settings)


@router.get("/auth/me", response_model=MeResponse)
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MeResponse:
    return MeResponse(
        user=UserPublic.model_validate(current_user),
        memberships=_memberships_for(db, current_user.id),
    )
