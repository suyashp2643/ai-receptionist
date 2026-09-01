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

## Phase 2 — Authentication, Multi-Tenancy & Isolation (complete, pending commit approval)

**Models** (`backend/app/models/`): `User` (global), `Tenant`, `TenantMember`
(unique on `(tenant_id, user_id)`), `RefreshToken` (rotation + reuse
detection). Native Postgres enums for `tenant_status`,
`tenant_member_role`, `tenant_member_status` — explicitly configured with
`values_callable` so the DB stores lowercase values matching the API
(SQLAlchemy's default would store the Python enum *name* instead). Full
schema: `docs/database-schema.md`.

**Migration**: one hand-reviewed Alembic revision
(`6c6136895656_create_users_tenants_tenant_members_.py`). Two issues found
and fixed during review before it was ever applied: (1) the enum-value
default described above, and (2) `downgrade()` needed explicit `DROP TYPE`
statements for all three enums — dropping a table does not drop the Postgres
enum type it used, so a downgrade→upgrade cycle would otherwise fail with
"type already exists." Verified end-to-end against the real
`ai_receptionist_dev` database: `upgrade head` → schema inspected column-by-
column (FKs, cascades, unique constraints, indexes, enum labels all
correct) → `downgrade -1` → `upgrade head` again, no errors. Connection
string was never printed at any point.

**Authentication**: Argon2id hashing (`argon2-cffi`), JWT access tokens
(HS256, algorithm whitelisted, `iss`/`aud` validated, 15 min default),
opaque SHA-256-hashed refresh tokens (256-bit random, 30 day default) with
rotation and family-wide revocation on reuse. Login/registration timing and
error messages are deliberately generic (see `docs/security.md`). Full
design: `docs/security.md`.

**Cookies & CSRF**: `HttpOnly`, environment-aware-`Secure`, `SameSite=Lax`
refresh cookie; separate non-`HttpOnly` CSRF cookie (stable per session,
not rotated); double-submit CSRF check applied only to `/auth/refresh` and
`/auth/logout` (the only cookie-authenticated state-changing routes).

**Tenant context & permissions**: `app/api/deps.get_tenant_context`
resolves role from the database using the `{tenant_id}` URL path parameter
only — never from the request body or JWT. `require_tenant_role(minimum)`
centralizes every permission check; no route file contains its own
role-name comparison. Non-member → `404`; insufficient role → `403` — a
deliberate distinction (see `docs/security.md`).

**Tenant-scoped repository**: `app/repositories/base.TenantScopedRepository`,
used by `TenantMemberScopedRepository` for the members-listing endpoint;
`User`/`Tenant` deliberately use separate plain repositories since they
aren't tenant-owned/are the scoping root.

**API endpoints** (`docs/api.md`): `POST /auth/{register,login,refresh,logout}`,
`GET /auth/me`, `POST /tenants`, `GET /tenants`, `GET /tenants/{id}`,
`PATCH /tenants/{id}`, `GET /tenants/{id}/members`.

**Frontend**: `/register`, `/login`, `/dashboard` (protected — redirects to
`/login` if a silent refresh on load fails), `src/lib/auth-context.tsx`
(access token in React state only, never `localStorage`), `src/lib/api.ts`
(attaches `Authorization` header, retries once through `/auth/refresh` on a
401, attaches the CSRF header for cookie-authenticated calls).

### Two real bugs found and fixed during test-writing (not just test bugs)

1. **`clear_auth_cookies` called before `raise HTTPException` was a no-op.**
   FastAPI discards the `response` object injected into a route function
   when that route raises — the exception handler builds an entirely new
   response. Any cookies "cleared" on the discarded object never reached the
   client. Fixed by returning a `JSONResponse` directly from the error path
   in `refresh()` instead of raising, so the cleared cookies are on the
   response that's actually sent. Caught by
   `test_logout_revokes_session_and_refresh_then_fails` and
   `test_refresh_token_reuse_revokes_entire_family` initially failing with
   stale-cookie symptoms.
2. **CSRF cookie was rotating on every refresh**, invalidating a header a
   client had legitimately just read. Fixed by making the CSRF cookie
   stable for the life of a session (refresh/logout re-set the *same* value
   instead of generating a new one) — simpler and just as secure, since
   only the refresh token itself needs rotation for reuse detection.

### Verification results (all passing)

- Backend: `pytest` **37/37** passed (auth, authorization, tenant-isolation
  at both HTTP and repository level, CORS), `ruff check` clean, `mypy`
  clean (41 files)
- `alembic current` / `upgrade head` / `downgrade -1` / `upgrade head`: all
  verified against `ai_receptionist_dev`, no errors, connection string
  never printed
- Frontend: `eslint` clean, `tsc --noEmit` clean, `next build` succeeded
  (`/`, `/register`, `/login`, `/dashboard` all prerendered)
- Widget: unchanged from Phase 1, still clean
- **Live integration check** (register → confirm owner membership → login →
  load `/me` and tenant → update tenant as owner → logout → confirm refresh
  rejected → confirm cross-tenant access rejected): all steps passed against
  the running backend + real database. Test data was cleaned up from
  `ai_receptionist_dev` afterward (confirmed by database name before
  deletion). No token, cookie, or password value was printed at any point.

### Known limitations / carried forward

- Invitation delivery (email invites) is explicitly out of scope — the
  `TenantMemberStatus.INVITED` value and `invited_at` column exist for
  forward compatibility but nothing sets them yet.
- No automated cleanup job for expired refresh tokens yet
  (`RefreshTokenRepository.delete_expired` exists as a helper, not wired to
  a scheduler).
- `docker-compose.yml` / Dockerfiles remain untested (carried from Phase 1).
- Frontend `postcss` advisory remains open (carried from Phase 1 — see
  above), unaffected by Phase 2 changes.
- Login-CSRF (an attacker forging a cross-site login request into their own
  account) is not separately mitigated — low severity, and out of scope for
  the double-submit pattern applied here (which targets cookie-authenticated
  actions, and login doesn't rely on a pre-existing cookie).

## Upcoming — Phase 3 (not started)

Industry templates, business settings, and knowledge/FAQ management.
Awaiting approval before starting.
