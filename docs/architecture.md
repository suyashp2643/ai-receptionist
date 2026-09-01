# Architecture

## Overview

AI Receptionist is a single, configurable multi-tenant engine — not a set of
per-industry applications. Industry behavior (terminology, welcome message,
suggested questions, qualification fields/rules, enabled actions, safety
rules, workflow stages) is **data** — implemented as of Phase 3 — resolved
at onboarding time from a global, versioned `IndustryTemplate` and snapshot
into a tenant's own `Receptionist`/`ReceptionistWorkflow` rows. There is no
industry-specific branching anywhere in the codebase: every route, service,
and validator is industry-agnostic and operates purely on the stored
configuration.

```
frontend/  Next.js 15 (App Router, TypeScript, Tailwind) — public site,
           onboarding, client dashboard
backend/   FastAPI (Python 3.12, Pydantic v2, SQLAlchemy 2.x, Alembic)
widget/    Embeddable receptionist widget — public API surface only
docs/      Architecture, API, security, progress documentation
scripts/   Safe local-dev and verification scripts
```

## Backend structure (Phase 3)

```
backend/app/
  main.py            Application factory (create_app)
  config.py          Environment-driven Settings (pydantic-settings)
  logging_config.py  Structured (JSON) logging setup
  db/
    base.py          Shared SQLAlchemy declarative Base
    session.py       Engine/session management, commit-on-success/
                      rollback-on-exception per request, check_database_connection()
  models/            User, Tenant, TenantMember, RefreshToken (Phase 2);
                      IndustryTemplate, BusinessProfile, Receptionist,
                      ReceptionistWorkflow, BusinessLocation, Service, FAQ,
                      KnowledgeSource/Document/Chunk (Phase 3) + mixins, enums
  repositories/      Plain (User, Tenant, TenantMember, IndustryTemplate,
                      BusinessProfile) and tenant-scoped (TenantScopedRepository
                      + one subclass per tenant-owned Phase 3 model)
  services/          auth_service.py, tenant_service.py (Phase 2);
                      onboarding_service.py, receptionist_service.py,
                      location_service.py, knowledge_service.py (Phase 3) —
                      business logic, independent of FastAPI/HTTP concerns
  seed_data/         industry_templates.py (10 versioned template
                      definitions), seed_runner.py (idempotent upsert),
                      demo_tenants.py (dev-only fictional demo seed)
  api/
    deps.py          get_current_user, get_tenant_context, require_tenant_role
    cookies.py       set_auth_cookies / clear_auth_cookies
    v1/
      router.py      Aggregates all v1 routers
      health.py, auth.py, tenants.py           (Phase 1/2)
      industry_templates.py, onboarding.py,
      receptionists.py, locations.py,
      services.py, faqs.py, knowledge.py       (Phase 3)
  core/
    errors.py          Central exception handlers (consistent error shape;
                        see docs/security.md for a Phase 3-discovered fix)
    security.py         Argon2 hashing, JWT encode/decode, refresh-token generation
    csrf.py              Double-submit CSRF dependency
    normalization.py     Email normalization
    allowlists.py        Server-maintained allow-lists (actions, field types,
                          rule types, mandatory safety rules, languages)
    text_safety.py        Plain-text validation/sanitization helpers
  schemas/             Pydantic request/response models, incl.
                        qualification.py (field/rule/working-hours schemas
                        shared across the whole Phase 3 surface)
```

`app/db/base.py` and the Alembic foundation from Phase 1 are exactly what
every subsequent phase's models plug into — no earlier scaffolding needed
to change.

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

## Tenant isolation model (implemented — Phase 2, extended in Phase 3)

Every tenant-owned table carries `tenant_id` and goes through
`TenantScopedRepository` (`app/repositories/base.py`), which filters every
query by a `tenant_id` that can only come from a trusted, server-resolved
`TenantContext` — never from client input. As of Phase 3 this covers eight
tenant-owned tables (`BusinessProfile`, `Receptionist`,
`ReceptionistWorkflow`, `BusinessLocation`, `Service`, `FAQ`,
`KnowledgeSource`, `KnowledgeDocument`, `KnowledgeChunk`), each with its own
thin repository subclass. Automated cross-tenant isolation tests run at both
the HTTP layer and the repository layer directly
(`backend/tests/tenant_isolation/`) for every one of them, and are part of
the standard verification suite. See `docs/security.md` and
`docs/database-schema.md` for detail, including the one case (`Service.location_id`)
where a client-supplied cross-reference needed its own explicit
same-tenant check beyond the URL path.

## Industry template & onboarding model (implemented — Phase 3)

`IndustryTemplate` is global, versioned catalog data — tenants can only
read it (no API route exists to mutate it). Selecting a template
(`POST /tenants/{id}/select-industry`) snapshots its current
`default_qualification_schema`/`default_actions`/`default_safety_rules`/
`default_workflow` into the tenant's own `ReceptionistWorkflow` row, only
when that workflow still looks untouched — so later edits to the global
template, or re-selecting a template, never silently overwrite a tenant's
customization. Onboarding progress (`GET /tenants/{id}/onboarding`) is
computed live from the tenant's actual stored data on every call rather
than tracked via a separate "current step" pointer, so it can never drift
out of sync with reality and survives a page refresh for free. See
`docs/api.md` and `docs/database-schema.md` for the full model/endpoint
detail.

## AI provider abstraction (Phase 4+)

A `Protocol`/ABC-based provider interface will support a development mock
(default, no credentials required), OpenAI, and Anthropic, selected via
environment configuration. All tests and demos must work on the mock
provider alone.
