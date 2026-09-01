# Progress

## Phase 0 — Architecture and Planning (complete)

Repository verified (root `/home/suyash/ai-product-suite/ai-receptionist`,
branch `main`, clean/empty). Full architecture, database design, API route
plan, frontend route plan, security/tenant-isolation strategy, and
phase-by-phase plan proposed and approved, along with four scoping decisions:

1. **Auth**: email/password only for MVP, Argon2 hashing, short-lived access
   tokens + secure refresh tokens, roles `owner`/`admin`/`member`, kept
   modular for a future swap to shared AI Business Engine auth.
2. **Integration secrets**: deferred to Phase 8; `IntegrationConnection`
   stores metadata/status only, no plaintext or placeholder secrets.
3. **Package tooling**: `python3 -m venv` + `pip` (requirements files, no
   Poetry/uv), npm for frontend/widget (no pnpm), Python 3.12, Node 24.
4. **Local dev**: non-Docker path is mandatory (Docker Desktop not
   installed); Redis optional in Phase 1; `docker-compose.yml` prepared for
   future use but not runtime-tested.

## Phase 1 — Frontend, Backend, Database & Testing Foundation (complete)

**Backend** (`backend/`): FastAPI app via an application factory
(`create_app`), environment-driven `Settings` (pydantic-settings),
structured JSON logging, central exception handlers with a consistent error
shape, `GET /health` and `GET /api/v1/health` reporting service + database
status, SQLAlchemy 2.x foundation (`Base`, lazy engine/session helpers, no
models yet), Alembic foundation (`alembic.ini`, `env.py` reading
`DATABASE_URL` from settings, no revisions yet), pytest suite (4 tests,
including a DB-unreachable → `degraded` path), ruff + mypy configured and
passing.

**Frontend** (`frontend/`): Next.js 15.5.25 (pinned — `create-next-app@latest`
would have installed Next 16, which is out of spec) with App Router,
TypeScript (strict), Tailwind CSS v4, ESLint 9. Home page renders an
`ApiHealthStatus` client component that fetches `NEXT_PUBLIC_API_URL +
/api/v1/health` and displays live status/environment/database info.

**Widget** (`widget/`): package foundation only — `package.json`, strict
`tsconfig.json`, ESLint flat config, a single typed `initWidget()` placeholder
export. No UI, no network calls yet (by design — full widget is Phase 5).

**Repo-level**: `.gitignore`, `.env.example` (backend + frontend vars,
clearly separated, nothing sensitive populated, Phase 8 keys commented out
for future reference), `README.md`, `docs/architecture.md`,
`docs/local-development.md` (non-Docker, primary path),
`docs/docker-setup.md` (future path, explicitly marked not runtime-tested),
`docker-compose.yml` + `backend/Dockerfile` + `frontend/Dockerfile` (syntax
validated only), `scripts/check.sh`, `scripts/dev_backend.sh`,
`scripts/dev_frontend.sh`.

### Verification results (all passing)

- Backend: `pytest` 4/4 passed, `ruff check` clean, `mypy` clean (15 files)
- Frontend: `eslint` clean, `tsc --noEmit` clean, `next build` succeeded
- Widget: `eslint` clean, `tsc --noEmit` clean, `tsc` build succeeded
- End-to-end connectivity: backend run on `:8000`, frontend run on `:3000`
  with `NEXT_PUBLIC_API_URL=http://localhost:8000`; confirmed
  `Access-Control-Allow-Origin: http://localhost:3000` on the API response,
  proving the frontend's browser-side fetch to the backend health endpoint
  will succeed. (Could not visually confirm in-app due to the review
  browser's network sandbox not reaching local WSL ports — see the Phase 1
  completion report for detail.)

### Real PostgreSQL verification (Phase 1 finalization)

A dedicated local PostgreSQL 16 development database (`ai_receptionist_dev`)
was provisioned by the user outside this session. `backend/.env` (untracked,
confirmed git-ignored before any credential was placed in it) now holds a
real `DATABASE_URL`. Two issues were found and fixed during setup, neither
of which required viewing or logging the password:

1. **Duplicate `DATABASE_URL` key** — the file initially had a real value on
   line 1 and an empty placeholder `DATABASE_URL=` left over from
   `.env.example`'s structure on line 17. Since dotenv parsing takes the
   *last* occurrence of a duplicate key, the empty line was silently winning
   and the app would have reported `not_configured`. Fixed by deleting the
   empty duplicate line (a blind line-delete by line number, no content
   review needed).
2. **Unencoded special character in the password** — the initial connection
   attempt failed with `OperationalError: Name or service not known`.
   Inspecting only the parsed `host`/`port`/`username` fields (never the
   password) showed the URL parser had absorbed part of the password into
   the host segment, because it contained an unencoded `@`. The user
   percent-encoded the special character(s) in the password directly in
   `backend/.env`.

After both fixes, `check_database_connection()` returned
`{'status': 'ok', 'detail': 'connected'}`, and both `GET /health` and
`GET /api/v1/health` confirmed:
```json
{"status": "ok", "service": "AI Receptionist API", "environment": "development",
 "database": {"status": "ok", "detail": "connected"}}
```
No password, password fragment, or full `DATABASE_URL` was printed, logged,
or committed at any point. The full verification suite (backend
pytest/ruff/mypy, frontend eslint/tsc/build, widget eslint/tsc/build) was
re-run against the live database and passed unchanged.

### Known limitations / carried-forward items

- `docker-compose.yml` / Dockerfiles are untested — no Docker Desktop
  installed here.
- See "Frontend dependency vulnerability" below for the `postcss` finding.

### Frontend dependency vulnerability (documented, not force-fixed)

- **Affected dependency**: `postcss@8.4.31`, bundled as Next.js's own
  **nested, exact-pinned** dependency at
  `frontend/node_modules/next/node_modules/postcss` (`next@15.5.25`
  declares `"postcss": "8.4.31"` with no range). This is a *separate copy*
  from the project's own top-level `postcss@8.5.26` (pulled in by
  `@tailwindcss/postcss`), which is already the latest, patched release.
- **Production vs. development**: `next` itself is a `dependencies` entry
  (needed at runtime to run `next start`), but postcss is only invoked by
  Next's internal build pipeline (`next build`) to compile CSS/source maps —
  it never runs against attacker-controlled input while the server is
  handling requests. So the practical exposure is build-time/tooling only,
  not a runtime attack surface of the deployed app.
- **Advisories**: XSS via unescaped `</style>` in CSS stringification, and
  three arbitrary-file-read / path-traversal issues via
  attacker-controlled `sourceMappingURL` in CSS comments (GHSA-qx2v-qp2m-jg93,
  GHSA-6g55-p6wh-862q, GHSA-fxqj-rqcc-2cmp, GHSA-r28c-9q8g-f849) — all fixed
  in postcss `>8.5.22`.
- **Safe, non-breaking patch availability**: `npm audit fix` only offers
  `next@16.3.4` (`isSemVerMajor: true`) because Next pins this nested copy
  exactly. **Not applied**, per instruction. A narrower alternative exists —
  npm's `"overrides"` field in `package.json` could pin every resolved
  `postcss` (including Next's nested copy) to `8.5.26` without touching
  Next's version at all, and without `--force`. This is plausible-safe (the
  project's own Tailwind toolchain already runs on `postcss@8.5.26` in the
  same tree with no issue) but **was not applied** — this step was scoped to
  documentation only. Recommend approving that `overrides` addition
  explicitly in a future step if desired, then re-running `npm audit` and
  the full frontend build/test suite to confirm no regression.

## Upcoming — Phase 2 (not started)

Multi-tenancy core: `Tenant`/`TenantMember` models, email/password auth
(Argon2, access + refresh tokens), tenant-scoped repository layer, and the
automated tenant-isolation test suite. Awaiting approval before starting.
