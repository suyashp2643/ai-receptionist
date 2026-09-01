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

## Backend structure (Phase 1)

```
backend/app/
  main.py            Application factory (create_app)
  config.py          Environment-driven Settings (pydantic-settings)
  logging_config.py  Structured (JSON) logging setup
  db/
    base.py          Shared SQLAlchemy declarative Base (no models yet)
    session.py        Engine/session management + check_database_connection()
  api/v1/
    router.py         Aggregates all v1 routers
    health.py          GET /health (also mounted at /api/v1/health)
  core/
    errors.py          Central exception handlers (consistent error shape)
  schemas/
    health.py           Pydantic response models for the health endpoint
```

No tenant, auth, or industry-template models exist yet — those are Phase 2/3
deliverables. `app/db/base.py` and the Alembic foundation exist now so those
phases only need to add model modules and run `alembic revision --autogenerate`.

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

## Authentication (planned for Phase 2 — not implemented yet)

Per approved Decision 1: secure email/password auth, Argon2 password hashing,
short-lived access tokens with a separate secure refresh-token flow, and
tenant membership + role enforcement (`owner`, `admin`, `member`). No
magic-link or OAuth in the MVP. The auth module will be isolated behind a
clear interface (`app/core/security.py` + a dedicated `auth` service) so it
can later be swapped for shared AI Business Engine authentication without
touching the rest of the application.

## Integration secrets (deferred to Phase 8)

Per approved Decision 2, `IntegrationConnection` (introduced in a later phase)
will store only non-sensitive metadata and status in Phase 1–7. No secret
storage mechanism is implemented yet. **Future requirement to satisfy before
Phase 8 ships:** integration credentials must be encrypted at rest (e.g. via
an application-level envelope key or a secrets manager) — never plaintext in
the database, never placeholder values checked into config.

## Tenant isolation model (Phase 2+)

Every tenant-owned table will carry `tenant_id`, and all reads/writes will go
through a tenant-scoped repository layer that injects the `tenant_id` filter
server-side — never trusted from client input. Automated cross-tenant
isolation tests will run as part of the standard verification suite from
Phase 2 onward. See the Phase 0 plan for the full entity list and API/route
plan.

## AI provider abstraction (Phase 4+)

A `Protocol`/ABC-based provider interface will support a development mock
(default, no credentials required), OpenAI, and Anthropic, selected via
environment configuration. All tests and demos must work on the mock
provider alone.
