# AI Receptionist

A configurable, multi-tenant AI receptionist platform. One core engine —
industry templates (real estate, clinics, hotels, restaurants, automotive,
law firms, education, home services, SaaS, custom) configure it via data,
not forked code.

Status: **Phase 9 — a final security/accessibility/responsive/production-
readiness audit** across every Phase 1–8 surface (see
docs/PROGRESS.md's Phase 9 section for the full report: five parallel
security-research passes finding no exploitable vulnerability in existing
code, five genuine gaps fixed — including wiring up widget visitor-session
revocation and two dialog-focus-restoration fixes — 29 new regression
tests, a dependency-advisory review, and live end-to-end browser
verification), on top of **Phase 8 — a secure integration foundation
(versioned event envelope/connectors/transactional outbox/delivery
worker, SSRF-guarded webhook delivery, encrypted secrets, a narrow
authenticated inbound API) connecting to Revenue Brain and a future AI
Sales Employee product, without importing from or coupling to either —
on top of Phase 7's public marketing website (Next.js route group,
centralized branding/pricing/SEO configuration) and three interactive
industry demos (clinic, hotel, real estate) embedding the real public
widget against dedicated fictional tenants, plus a zero-cost public
lead-capture endpoint, itself on top of Phase 6's client operations
dashboard: real analytics, conversation/contact/enquiry/appointment/
handoff management, internal notes, an audit log, role-based
permissions, and CSV export, itself on top of Phase 5's public
embeddable website widget, browser voice, secure public conversations,
contact capture, appointment requests, human handoff, and installation
management**. See [docs/PROGRESS.md](docs/PROGRESS.md) for what's
implemented so far, [docs/architecture.md](docs/architecture.md) for the
system design, and [docs/security.md](docs/security.md) for the
auth/tenant-isolation/public-widget threat model.

## Stack

- Frontend: Next.js 15 (App Router, TypeScript, Tailwind CSS)
- Backend: FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic (Python 3.12)
- Auth: Argon2id password hashing, JWT access tokens, rotating opaque refresh tokens
- Database: PostgreSQL (required from Phase 2 for auth/tenant endpoints; optional for `/health`)
- Cache/queue: Redis (optional; not required — the public widget's rate
  limiter ships an in-process, single-process implementation behind a
  Protocol a future Redis adapter can satisfy without call-site changes)
- Widget (Phase 5): dependency-free embeddable TypeScript package, bundled
  with esbuild into one ~25KB IIFE (`widget/dist/widget.js`) — Shadow DOM
  UI, SSE streaming, browser-native voice (Web Speech API), contact/
  appointment/handoff forms
- AI conversation engine (Phase 4): provider-abstracted, defaults to a
  deterministic zero-cost mock provider — real providers (OpenAI, Anthropic)
  exist only as disabled adapters until credentials are configured; the
  public widget (Phase 5) reuses this engine unchanged
- Client operations dashboard (Phase 6): tenant-scoped analytics computed
  live via explicit SQL aggregates (no cache, no background job), a
  conversation/contact/enquiry/appointment/handoff management surface,
  staff-only internal notes, an append-only activity/audit log, and
  owner/admin-only CSV export — all on the existing Postgres database and
  mock AI provider, no new external service
- Public marketing website & demos (Phase 7): a `(marketing)` Next.js route
  group (`/`, `/product`, `/industries/*`, `/demo/*`, `/pricing`,
  `/security`, `/about`, `/contact`, `/privacy`, `/terms`) that never wraps
  in the dashboard's `AuthProvider` and never receives a dashboard cookie;
  centralized branding/pricing/demo/SEO config modules
  (`frontend/src/lib/{brand,pricing,demos,seo}.ts`); three fictional,
  user-less demo tenants (`backend/app/seed_data/public_demo_tenants.py`)
  embedding the real, unmodified public widget bundle via a sandboxed
  static page (`frontend/public/demo-widget.html`, modeled on Phase 5's
  dashboard live-preview mechanism); a global, non-tenant-owned
  `public_leads` model behind a rate-limited, honeypot-protected endpoint
  with no public read API
- Secure integration foundation (Phase 8): a versioned event envelope and
  twelve outbound event types (`app/integrations/envelope.py`), four
  connector types (mock/webhook/revenue_brain/sales_employee) sharing one
  HMAC-SHA256 signing scheme, a transactional outbox +
  `FOR UPDATE SKIP LOCKED` delivery worker (no message broker — see
  `scripts/process_integration_outbox.py`), an SSRF guard
  (`app/core/ssrf_guard.py`) rejecting private/loopback/link-local/
  reserved ranges plus connection-level IP pinning to close the
  validate-then-connect TOCTOU gap, Fernet-encrypted secrets at rest, and
  a narrow, API-key-authenticated inbound API that can never mutate a
  business record — all managed from an authenticated dashboard UI
  (`/dashboard/integrations/*`) with a one-click, zero-network
  integration lab and tenant-scoped health/observability. Full contract:
  `docs/integration-contracts.md`.
- Zero-cost by design through Phase 8: no paid APIs, no external embeddings,
  no telephony/SMS/email providers, no paid analytics/fonts/hosting, no
  message broker — deterministic local chunking + PostgreSQL full-text
  search for knowledge, deterministic mock AI provider, browser-native
  (not server-side) voice, an in-process outbox worker instead of Kafka/
  RabbitMQ/Celery

## Repository layout

```
frontend/   Next.js app — public site, onboarding, dashboard
backend/    FastAPI app — API, models, AI orchestration
widget/     Embeddable receptionist widget
docs/       Architecture, API, security, progress docs
scripts/    Local dev + verification scripts
```

## Getting started

Docker Desktop is not required (and not currently used) for local
development. Follow [docs/local-development.md](docs/local-development.md)
for the supported non-Docker setup on Ubuntu/WSL. A future Docker Compose
path is documented in [docs/docker-setup.md](docs/docker-setup.md) but has
not been runtime-tested yet.

Quick start:

```bash
# Backend
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
cp ../.env.example .env
# Edit backend/.env: set DATABASE_URL to your own Postgres instance, then:
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(64))" >> .env
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
cp ../.env.example .env.local
npm run dev
```

Then open http://localhost:3000 — the home page shows live backend health,
and you can register a workspace at `/register` or log in at `/login`. A
new workspace walks through onboarding at `/onboarding/business` before
reaching the dashboard.

Seed the global industry-template catalog (required before onboarding can
select a template):

```bash
cd backend && .venv/bin/python scripts/seed_industry_templates.py
```

Optionally seed three fictional demo tenants for exploring the dashboard
(development only, never run in production):

```bash
cd backend && .venv/bin/python scripts/seed_demo_data.py
```

Seed the three fictional, user-less tenants the public `/demo/*` pages
embed (development only, idempotent, no password anywhere):

```bash
cd backend && .venv/bin/python scripts/seed_public_demos.py
```

## Verification

```bash
./scripts/check.sh
```

Runs backend tests/lint/type-check, frontend lint/type-check/build, and
widget lint/type-check/build.

## Contributing conventions

- Every tenant-owned database row carries `tenant_id`; never bypass
  `TenantScopedRepository` (`backend/app/repositories/base.py`) for tenant-owned data.
- Role checks belong in `app/api/deps.require_tenant_role` only — never
  scattered `if role == "..."` checks in route files.
- No secrets in code or committed `.env` files — see `.env.example`. Generate
  `JWT_SECRET_KEY` with `secrets.token_urlsafe(64)` directly into the ignored `backend/.env`.
- No destructive Alembic migrations run automatically; every autogenerated
  migration is hand-reviewed (see `docs/database-schema.md` for the enum
  gotchas this project already worked around once).
- The AI conversation engine (Phase 4) works fully on a development mock
  provider with zero paid API credentials; keep it that way for every test
  and demo. Real providers are disabled adapters until explicitly configured.
