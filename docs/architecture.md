# Architecture

## Overview

AI Receptionist is a single, configurable multi-tenant engine — not a set of
per-industry applications. Industry behavior (terminology, welcome message,
suggested questions, qualification fields/rules, enabled actions, safety
rules, appointment/handoff workflow) is **data**, resolved at runtime from an
`IndustryTemplate` plus a tenant's own `Receptionist`/`ReceptionistWorkflow`
overrides — not branched application code.

```
frontend/  Next.js 15 (App Router, TypeScript, Tailwind) — public site,
           onboarding, client dashboard
backend/   FastAPI (Python 3.12, Pydantic v2, SQLAlchemy 2.x, Alembic)
widget/    Embeddable receptionist widget — public API surface only
docs/      Architecture, API, security, progress documentation
scripts/   Safe local-dev and verification scripts
```

## Backend structure (Phase 2)

```
backend/app/
  main.py            Application factory (create_app)
  config.py          Environment-driven Settings (pydantic-settings)
  logging_config.py  Structured (JSON) logging setup
  db/
    base.py          Shared SQLAlchemy declarative Base
    session.py       Engine/session management, commit-on-success/
                      rollback-on-exception per request, check_database_connection()
  models/            User, Tenant, TenantMember, RefreshToken (+ mixins, enums)
  repositories/      Plain (User, Tenant, TenantMember) and tenant-scoped
                      (TenantScopedRepository + TenantMemberScopedRepository)
  services/          auth_service.py, tenant_service.py — business logic,
                      independent of FastAPI/HTTP concerns
  api/
    deps.py          get_current_user, get_tenant_context, require_tenant_role
    cookies.py       set_auth_cookies / clear_auth_cookies
    v1/
      router.py      Aggregates all v1 routers
      health.py      GET /health (also mounted at /api/v1/health)
      auth.py        register/login/refresh/logout/me
      tenants.py     tenant CRUD + membership listing
  core/
    errors.py        Central exception handlers (consistent error shape)
    security.py      Argon2 hashing, JWT encode/decode, refresh-token generation
    csrf.py           Double-submit CSRF dependency
    normalization.py  Email normalization
  schemas/           Pydantic request/response models (health, user, auth, tenant)
```

Industry-template models are still Phase 3. `app/db/base.py` and the
Alembic foundation from Phase 1 are exactly what Phase 2's models plugged
into — no earlier scaffolding needed to change.

## Database connectivity model

`DATABASE_URL` is optional at the settings level. `check_database_connection()`
distinguishes three states, all handled without raising:

- `not_configured` — no `DATABASE_URL` set (expected in a fresh checkout)
- `ok` — connected successfully
- `unavailable` — configured but unreachable (connection refused, timeout, etc.)

The `/health` and `/api/v1/health` endpoints report `status: "ok"` when the
database is either connected or simply not configured yet, and
`status: "degraded"` only when it's configured but unreachable — so the
service never crashes or 500s because the database is temporarily down.

## Authentication (implemented — Phase 2)

Secure email/password auth: Argon2id password hashing, short-lived JWT
access tokens (in-memory on the frontend, never `localStorage`), rotating
opaque refresh tokens (`HttpOnly` cookie) with reuse detection, and tenant
membership + role enforcement (`owner`, `admin`, `member`). No magic-link or
OAuth in the MVP. The auth module is isolated behind three replaceable seams
(token issuance, user storage, session mechanics) so it can later be
swapped for shared AI Business Engine authentication without touching
tenant/permission logic. Full detail: `docs/security.md`.

## Integration secrets (deferred to Phase 8)

Per approved Decision 2, `IntegrationConnection` (introduced in a later phase)
will store only non-sensitive metadata and status in Phase 1–7. No secret
storage mechanism is implemented yet. **Future requirement to satisfy before
Phase 8 ships:** integration credentials must be encrypted at rest (e.g. via
an application-level envelope key or a secrets manager) — never plaintext in
the database, never placeholder values checked into config.

## Tenant isolation model (implemented — Phase 2)

`Tenant` and `TenantMember` exist now; every future tenant-owned table will
carry `tenant_id` and go through `TenantScopedRepository`
(`app/repositories/base.py`), which filters every query by a `tenant_id`
that can only come from a trusted, server-resolved `TenantContext` — never
from client input. Automated cross-tenant isolation tests run at both the
HTTP layer and the repository layer directly (`backend/tests/tenant_isolation/`)
and are part of the standard verification suite from Phase 2 onward. See
`docs/security.md` and `docs/database-schema.md` for detail.

## AI provider abstraction (Phase 4+)

A `Protocol`/ABC-based provider interface will support a development mock
(default, no credentials required), OpenAI, and Anthropic, selected via
environment configuration. All tests and demos must work on the mock
provider alone.
