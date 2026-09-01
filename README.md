# AI Receptionist

A configurable, multi-tenant AI receptionist platform. One core engine —
industry templates (real estate, clinics, hotels, restaurants, automotive,
law firms, education, home services, SaaS, custom) configure it via data,
not forked code.

Status: **Phase 1 — foundation**. See [docs/PROGRESS.md](docs/PROGRESS.md)
for what's implemented so far and [docs/architecture.md](docs/architecture.md)
for the system design.

## Stack

- Frontend: Next.js 15 (App Router, TypeScript, Tailwind CSS)
- Backend: FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic (Python 3.12)
- Database: PostgreSQL (optional in Phase 1)
- Cache/queue: Redis (optional; not required until later phases)
- Widget: embeddable TypeScript package (foundation only so far)

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
.venv/bin/python -m uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
cp ../.env.example .env.local
npm run dev
```

Then open http://localhost:3000 — the home page shows live backend health.

## Verification

```bash
./scripts/check.sh
```

Runs backend tests/lint/type-check, frontend lint/type-check/build, and
widget lint/type-check/build.

## Contributing conventions

- Every tenant-owned database row will carry `tenant_id`; never bypass the
  tenant-scoped repository layer once it exists (Phase 2+).
- No secrets in code or committed `.env` files — see `.env.example`.
- No destructive Alembic migrations run automatically.
- The AI conversation engine (Phase 4+) must work fully on a development
  mock provider with zero paid API credentials.
