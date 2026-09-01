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
overall service status stays `"ok"`.

To connect a real database, set:

```
DATABASE_URL=postgresql+psycopg://<user>:<password>@localhost:5432/<database>
```

using credentials for a PostgreSQL instance you control (e.g. `sudo -u
postgres createuser` / `createdb` on your own machine, or a role you already
have). This project never ships or assumes a default password.

### Redis (optional in Phase 1)

`REDIS_URL` is not read by any Phase 1 code path. The backend and its health
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
eslint/tsc/build in sequence.
