# Local Development (non-Docker path — primary/mandatory)

Docker Desktop is not installed in this environment, so this is the
supported workflow. All commands assume Ubuntu-24.04 WSL with:

- Node.js 24.x, npm 11.x
- Python 3.12.x
- PostgreSQL client (`psql`) — a local PostgreSQL server is optional; the
  backend runs and reports healthy without one

## 1. Backend

```bash
cd backend
python3 -m venv .venv

# If `python3 -m venv` fails with "ensurepip is not available", either:
#   sudo apt install python3.12-venv     (requires sudo — ask your admin if unavailable)
# or bootstrap pip without sudo:
#   python3 -m venv --without-pip .venv
#   curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
#   .venv/bin/python3 /tmp/get-pip.py

.venv/bin/python -m pip install -r requirements-dev.txt
cp ../.env.example .env   # then edit backend/.env as needed
.venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or simply: `./scripts/dev_backend.sh` (from the repo root).

Verify: `curl http://localhost:8000/health` and
`curl http://localhost:8000/api/v1/health`.

### Enabling PostgreSQL

Leave `DATABASE_URL` unset in `backend/.env` to run without a database — the
health endpoint reports `"database": {"status": "not_configured"}` and the
overall service status stays `"ok"`. **From Phase 2 onward, auth and tenant
endpoints require a real database** — only `/health` and `/api/v1/health`
work without one.

To connect a real database, set:

```
DATABASE_URL=postgresql+psycopg://<user>:<password>@localhost:5432/<database>
```

using credentials for a PostgreSQL instance you control (e.g. `sudo -u
postgres createuser` / `createdb` on your own machine, or a role you already
have). This project never ships or assumes a default password. **If your
password contains special characters** (`@ : / ? # %`), percent-encode them
in the URL (`@` → `%40`, etc.) — an unencoded `@` in particular will silently
corrupt host parsing rather than fail loudly.

Then apply migrations (see "Database migrations" below) before using any
auth/tenant endpoint.

### Authentication configuration

Generate a signing secret and set it directly in the ignored `backend/.env`
— never paste it into chat, a commit, or any other tracked file:

```bash
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(64))" >> backend/.env
```

`JWT_ISSUER`, `JWT_AUDIENCE`, `ACCESS_TOKEN_TTL_MINUTES`,
`REFRESH_TOKEN_TTL_DAYS`, `COOKIE_SECURE`, `COOKIE_SAMESITE`,
`REFRESH_COOKIE_NAME`, `CSRF_COOKIE_NAME` all have sensible defaults (see
`.env.example`) and don't need to be set for local development.

### Database migrations

```bash
cd backend
.venv/bin/python -m alembic current      # what's currently applied
.venv/bin/python -m alembic upgrade head # apply pending migrations
```

Never run migrations against anything but your own dedicated development
database. See `docs/database-schema.md` for the reviewed migration's
contents and the enum-handling gotchas it works around.

### Redis (optional through Phase 2)

`REDIS_URL` is not read by any code path yet. The backend and its health
checks run correctly with no Redis installed or configured. Redis becomes
relevant starting Phase 4/5 (rate limiting, SSE pub/sub, caching).

## 2. Frontend

```bash
cd frontend
npm install
cp ../.env.example .env.local   # keep only the NEXT_PUBLIC_* lines you need
npm run dev
```

Or simply: `./scripts/dev_frontend.sh`.

Open http://localhost:3000 — the home page's "Backend API status" panel
calls `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`) and shows the
live result of `/api/v1/health`.

## 3. Widget (foundation only in Phase 1)

```bash
cd widget
npm install
npm run build   # compiles src/index.ts -> dist/
```

There is no runnable UI yet — see `widget/src/index.ts` for the current
placeholder export and Phase 5 plan.

## 4. Running all checks

```bash
./scripts/check.sh
```

Runs backend pytest/ruff/mypy, frontend eslint/tsc/build, and widget
eslint/tsc/build in sequence. **From Phase 2 onward, `pytest` requires a
real database** configured and migrated (see above) — auth/tenant/
tenant-isolation tests use it directly, wrapped in a rolled-back transaction
per test (see `backend/tests/conftest.py`), and refuse to run at all against
any database whose name isn't `ai_receptionist_dev`.

Health-only tests (`backend/tests/test_health.py`) still work with no
database configured at all, preserving the Phase 1 guarantee.
