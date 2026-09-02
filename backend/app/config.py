from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven application configuration.

    No credentials are hardcoded here. DATABASE_URL is optional so the
    service can boot and report health even before a database is provisioned.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI Receptionist API"
    environment: str = "development"
    debug: bool = True

    database_url: str | None = None

    cors_allow_origins: str = "http://localhost:3000"

    log_level: str = "INFO"

    # --- Authentication (Phase 2) ---
    # No default secret is provided in a non-development environment: a
    # missing JWT_SECRET_KEY outside development is a startup-time error
    # (see get_settings validation below), never a silently-guessable default.
    jwt_secret_key: str | None = None
    jwt_issuer: str = "ai-receptionist"
    jwt_audience: str = "ai-receptionist-clients"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    # Small, deliberate tolerance for wall-clock disagreement between the
    # process that signs a token and the process that verifies it —
    # applied only to PyJWT's time-based claim checks (iat/nbf/exp), never
    # to signature/issuer/audience. Root-caused via live reproduction (a
    # tight create-then-immediately-decode loop, no test framework, no
    # mocking involved): roughly 1 in 100,000-200,000 iterations, this
    # environment's wall clock produced a `now()` reading 600-700ms
    # *earlier* than one taken a fraction of a second before — consistent
    # with a VM host time-sync correction — which PyJWT's zero-leeway
    # default treated as "issued in the future" (`ImmatureSignatureError`)
    # for a token that was, in reality, valid at the instant it was
    # issued. 5 seconds is roughly 7-8x the largest skew actually observed
    # (~0.7s) — enough margin for that class of correction without
    # meaningfully weakening `exp`: it can only make an expired token
    # valid for 5 more seconds out of a 900-second (15-minute) lifetime,
    # about 0.6% of it. See docs/security.md for the full incident and
    # trade-off writeup.
    jwt_clock_skew_leeway_seconds: float = 5.0

    # --- Cookie security (environment-aware) ---
    # cookie_secure defaults to True everywhere except local development, so
    # production never accidentally ships a non-Secure cookie.
    cookie_secure: bool | None = None
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    refresh_cookie_name: str = "ai_receptionist_refresh"
    csrf_cookie_name: str = "ai_receptionist_csrf"

    # --- AI conversation engine (Phase 4) ---
    # Deliberately a plain str, not a Literal — provider resolution
    # (app/ai/providers/factory.py) validates it explicitly and raises a
    # controlled ProviderConfigurationError for an unknown name, which is
    # both more testable and produces a clearer error than a raw pydantic
    # validation failure at settings-parse time.
    ai_provider: str = "mock"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    ai_provider_timeout_seconds: float = 30.0
    max_conversation_message_length: int = 4000
    max_conversation_context_chars: int = 12000
    retrieval_result_limit: int = 5
    sse_heartbeat_seconds: float = 15.0

    # --- Public widget (Phase 5) ---
    # A visitor capability token's lifetime — independent of the dashboard
    # JWT's access_token_ttl_minutes above. Deliberately longer than a
    # dashboard session since a widget visitor may leave a tab open for a
    # while mid-conversation; still bounded, and always revocable via
    # WidgetVisitorSession.revoked_at.
    widget_visitor_session_ttl_hours: int = 24
    # Hard ceiling on messages in one widget conversation — bounds worst-case
    # per-conversation cost/storage regardless of rate limiting.
    widget_max_messages_per_conversation: int = 200
    # Where the embeddable widget bundle is served from — used both for the
    # dashboard's "copy embed code" snippet AND its live local preview
    # iframe (see docs/architecture.md), which actually fetches this URL.
    # Phase 5 ships no production hosting: this defaults to a local dev URL
    # matching docs/local-development.md's documented
    # `cd widget && python3 -m http.server 5174` command — which serves the
    # whole `widget/` directory, putting the built bundle at `/dist/widget.js`
    # relative to that root, not bare `/widget.js`. A real deployment would
    # typically serve `dist/widget.js` at a bare URL root (e.g. a CDN), so
    # this is a dev-only path, not a production convention. The
    # dashboard/docs must not claim production bundle hosting exists until
    # one is actually deployed.
    widget_bundle_url: str = "http://localhost:5174/dist/widget.js"
    # See app/core/client_identity.py's docstring — only set True when a
    # trusted proxy in front of this app sets (and strips any inbound)
    # X-Forwarded-For itself.
    trust_proxy_headers: bool = False
    # The dashboard's own origin(s) — trusted for the "live local preview"
    # feature (app/dashboard/receptionist/widget) regardless of what a
    # tenant has configured in their own WidgetInstallation.allowed_domains.
    # Deliberately a SEPARATE setting from cors_allow_origins (even though
    # they hold the same value in this deployment): one governs the
    # dashboard-API's own CORS policy, the other is a widget-specific,
    # platform-level trust decision — conflating them would make a future
    # change to one silently change the other. Never merged into any
    # tenant's allowed_domains; see app/api/widget_deps.validate_widget_origin.
    platform_preview_origins: str = "http://localhost:3000"

    # --- Data retention defaults (Phase 5) ---
    # These are DECLARED DEFAULTS ONLY — no scheduled job or code path in
    # this codebase currently reads or acts on them to delete anything.
    # Every record type below requires manual deletion today (see
    # docs/security.md's "Retention" section for the full, honest
    # accounting of what that means operationally). They exist now so a
    # future deletion job has one already-reviewed, tenant-independent
    # place to read defaults from, rather than each such job inventing its
    # own number. None of these values implies, and nothing in this
    # product claims, compliance with any data-protection regulation.
    widget_visitor_session_retention_days: int = 30
    widget_conversation_retention_days: int = 90
    contact_and_enquiry_retention_days: int = 365
    appointment_request_retention_days: int = 180
    handoff_request_retention_days: int = 180

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def platform_preview_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.platform_preview_origins.split(",") if origin.strip()]

    @property
    def resolved_cookie_secure(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.environment != "development"

    def require_jwt_secret(self) -> str:
        """Raises at call time (not import time) if no signing secret is configured.

        Keeping this lazy means the app can still boot (e.g. for /health) in an
        environment where auth hasn't been configured yet, but any actual auth
        operation fails loudly instead of silently using a guessable default.
        """
        if not self.jwt_secret_key:
            raise RuntimeError(
                "JWT_SECRET_KEY is not set. Generate one and set it in backend/.env "
                "(see .env.example) before using authentication endpoints."
            )
        return self.jwt_secret_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
