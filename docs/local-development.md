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
`JWT_CLOCK_SKEW_LEEWAY_SECONDS` (see docs/security.md's "Clock-skew leeway"
section — matters more in a VM-based dev environment like WSL2 than on
bare metal), `REFRESH_TOKEN_TTL_DAYS`, `COOKIE_SECURE`, `COOKIE_SAMESITE`,
`REFRESH_COOKIE_NAME`, `CSRF_COOKIE_NAME` all have sensible defaults (see
`.env.example`) and don't need to be set for local development.

### Database migrations

```bash
cd backend
.venv/bin/python -m alembic current      # what's currently applied
.venv/bin/python -m alembic upgrade head # apply pending migrations
```

Never run migrations against anything but your own dedicated development
database. See `docs/database-schema.md` for the reviewed migrations'
contents and the enum-handling gotchas they work around.

### Seed data

Seed the global industry-template catalog — required before onboarding can
select a template (idempotent, safe to re-run):

```bash
cd backend
.venv/bin/python scripts/seed_industry_templates.py
```

Optionally, seed three fictional demo tenants (a real estate agency, a
dental clinic, a boutique hotel) fully onboarded with a location, services,
an FAQ, and a knowledge document each — **development only**, refuses to
run unless `ENVIRONMENT=development`, idempotent:

```bash
cd backend
.venv/bin/python scripts/seed_demo_data.py
```

This prints a freshly generated one-time password per demo user directly to
your terminal — it is never written to any file or tracked document, so
save it if you want to log in as that demo tenant.

### Redis (still optional through Phase 4)

`REDIS_URL` is not read by any code path yet — Phase 4's SSE streaming is a
single synchronous per-request generator, not a pub/sub fan-out, so it
needed no Redis either. The backend and its health checks run correctly
with no Redis installed or configured.

### AI provider configuration (Phase 4)

`AI_PROVIDER=mock` (the default — leaving it unset also means mock) requires
**no API key, no network access, and no cost**. Every automated test, the
private test console, and this whole phase's demos run entirely on it.
`OPENAI_API_KEY`/`ANTHROPIC_API_KEY` are optional placeholders in
`.env.example` for a later phase — setting `AI_PROVIDER=openai` or
`AI_PROVIDER=anthropic` without the matching key produces a clear
`ProviderConfigurationError` at startup/request time rather than a silent
fallback or an attempted call with an empty key. Do not set a real key in
any tracked file; `backend/.env` is gitignored for exactly this reason.

`AI_PROVIDER_TIMEOUT_SECONDS`, `MAX_CONVERSATION_MESSAGE_LENGTH`,
`MAX_CONVERSATION_CONTEXT_CHARS`, `RETRIEVAL_RESULT_LIMIT`, and
`SSE_HEARTBEAT_SECONDS` all have sensible defaults (see `.env.example`) and
don't need to be set for local development.

### Using the private test console

1. Complete onboarding for a tenant (business profile + at least one active
   FAQ or knowledge document + an active receptionist) — the dashboard's
   "Finish setting up your receptionist" prompt links directly to whatever
   step is still incomplete.
2. From the dashboard, open **"Open the private test console (mock AI
   demonstration)"** (`/dashboard/receptionist/test`).
3. Pick a receptionist and click **Start new conversation** — this is real,
   persisted backend data (not a frontend-only mock transcript). Send
   messages, watch qualification/citations/tool-activity/safety panels
   update live, and use **Complete conversation** to generate and view the
   stored summary. **Reload an existing test conversation** restores any
   past conversation's full transcript and summary from the database.
4. This route requires an authenticated tenant member — it is not the
   public embeddable widget. For the public, unauthenticated-beyond-a-
   capability-token equivalent (Phase 5), see "3. Widget" below.

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

## 3. Widget (Phase 5)

```bash
cd widget
npm install
npm run build    # tsc -p tsconfig.json — type declarations to dist/*.d.ts
npm run bundle   # esbuild -> dist/widget.js (the embeddable IIFE, ~25KB minified)
npm test         # vitest — watch mode
npm run test:run # vitest — single run
```

`npm run bundle` requires esbuild's native binary; if `npm install` reports
`allow-scripts pending` for `esbuild`, approve its postinstall script once
(it only downloads esbuild's own platform binary, nothing external to the
package):

```bash
npm approve-scripts esbuild
```

### Trying the widget against a real backend

**Fastest path**: once an installation is created and activated in the
dashboard (`/dashboard/receptionist/widget`), its "Live local preview"
panel embeds the real widget bundle against the real backend directly in
the dashboard — no separate static server or demo page needed. It only
requires `widget/dist/widget.js` to actually exist (`cd widget && npm run
bundle`) and be reachable at the installation's `widget_bundle_url`
(`http://localhost:5174/dist/widget.js` by default, matching step 3
below's `python3 -m http.server 5174` served from the `widget/` directory
root — **not** a bare `/widget.js` path, which found a real bug during
Phase 5 follow-up live verification: the two defaults originally
disagreed, and the dashboard preview's browser request for the bundle
failed with `ERR_BLOCKED_BY_ORB` against a 404). The steps below are for
testing the snippet on a genuinely separate page, the way a real
customer's site would embed it.

1. Start the backend (`AI_PROVIDER=mock` is the default — no key needed) and
   register a tenant, business profile, and an **active** receptionist — the
   same steps `docs/PROGRESS.md`'s live E2E script walks through, or just
   use the dashboard.
2. In the dashboard, create and **activate** a widget installation
   (`/dashboard/receptionist/widget`) with `localhost` in its allowed
   domains — `localhost` is only accepted while the backend's
   `ENVIRONMENT=development` (see `docs/security.md`). Copy its `public_id`
   from the installation list or the embed snippet.
3. Serve the `widget/` directory itself (so both the demo page and the
   bundle are reachable from one origin) on the port
   `Settings.widget_bundle_url` expects by default (`5174`):
   ```bash
   cd widget && python3 -m http.server 5174
   ```
4. Edit `widget/demo/index.html`'s `data-receptionist-id` to the `public_id`
   from step 2 (it already points `src` at `../dist/widget.js` and
   `data-api-base-url` at `http://localhost:8000`), then open
   `http://localhost:5174/demo/index.html` in a browser. This file is a
   plain static host page standing in for a real customer's website — it is
   not served by, or part of, the product itself.
5. Rebuild the bundle (`npm run bundle`) after any `src/` change and reload
   the demo page — there is no watch/hot-reload for the bundle step.

A capability token issued by `POST .../sessions` is stored in
`sessionStorage` (not `localStorage`, not a cookie — see
docs/security.md), scoped per `public_id`; clearing it
(`sessionStorage.clear()` in devtools, or a private/incognito window) forces
a fresh conversation on next open instead of resuming.

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

### Test categories (Phase 4)

Three distinct categories now exist, each with a different DB relationship:

| Category | Example files | DB behavior |
|---|---|---|
| Fast unit tests | `test_ai_providers.py`, `test_ai_safety.py`, `test_ai_qualification.py`, `test_ai_system_instructions.py`, `test_db_session_lifecycle.py`, `test_streaming_generator_lifecycle.py` | No database at all |
| Normal API tests | `test_auth.py`, `test_tenants.py`, `test_conversations_api.py`, everything else under `tests/` | One shared, rolled-back-at-the-end SQLAlchemy session per test (`db_backed_client`) — fast and fully isolated, but collapses what would be several independently-pooled production connections into one |
| **PostgreSQL multi-connection integration tests** | `backend/tests/integration/test_conversation_concurrency.py` | Each simulated request gets its **own** freshly-checked-out connection from the real pool (`real_client` — no dependency override), and commits real rows to `ai_receptionist_dev` that the test itself deletes afterward |

```bash
cd backend
.venv/bin/python -m pytest -q                # complete suite — includes all three categories
.venv/bin/python -m pytest -m multiconn -v    # only the multi-connection integration tests
.venv/bin/python -m pytest -m "not multiconn" -q  # everything except them (fast, no real commits)
```

`pytest -q` (and `./scripts/check.sh`) **never filters the multi-connection
tests out** — they run by default whenever `DATABASE_URL` is configured,
exactly like every other database-backed test, and are only skipped (with
an explicit, visible pytest `SKIPPED`, never silently) when no database is
configured at all. If they end up skipped in an environment where
`DATABASE_URL` *is* set, something is wrong with that environment, not with
the suite — do not treat that as "tests passed."

### Why the multi-connection tests exist and how they differ

`tests/conftest.py`'s `db_backed_client` fixture deliberately shares one
session across every request in a test, which is exactly what let three
real Phase 4 concurrency/connection-lifecycle bugs pass 255/255 unit tests
before being found live (see docs/architecture.md and docs/PROGRESS.md).
`backend/tests/integration/` exists specifically to catch a regression of
any of those three bugs automatically: `real_client` uses the app's real,
unmodified `get_db` dependency, so every simulated request gets a
genuinely separate `Session`/pooled connection, and tests that need true
overlapping execution (not just sequential separate connections) submit
requests through a `ThreadPoolExecutor` with a bounded `.result(timeout=...)`
— a real lock regression fails the test with a clear timeout rather than
hanging the run. Every test that registers a tenant hands its id (and its
owning user id) to the `cleanup_tenants` fixture, which re-verifies the
database name and deletes exactly those rows — cascading to their
conversations/messages/receptionists — once the test finishes, pass or
fail; nothing broader is ever truncated or reset.
