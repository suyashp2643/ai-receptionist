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

## Phase 2 — Authentication, Multi-Tenancy & Isolation (complete, commit `65c9c92`)

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

## Phase 3 — Industry Templates, Onboarding & Business Configuration (complete)

Built entirely at zero cost — no paid APIs, no external embeddings; the
knowledge search relies solely on PostgreSQL's built-in full-text search.

**Models** (`backend/app/models/`): `IndustryTemplate` (global, `UNIQUE(key,
version)`), `BusinessProfile` (tenant-owned, 1:1 with `Tenant`),
`Receptionist` + `ReceptionistWorkflow` (1:1 for the MVP — created together
atomically), `BusinessLocation` (partial unique index enforcing ≤1 primary
per tenant at the DB level), `Service`, `FAQ`, `KnowledgeSource` /
`KnowledgeDocument` / `KnowledgeChunk`. Four new native Postgres enums
(`onboarding_status`, `receptionist_status`, `content_status`,
`knowledge_source_type`), all with `values_callable` for lowercase storage.
Full schema: `docs/database-schema.md`.

**Migration**: one hand-reviewed Alembic revision
(`0f245f269b1d_add_industry_templates_onboarding_...py`) on top of Phase 2's
head, verified upgrade → downgrade → upgrade against `ai_receptionist_dev`
with the same enum-type-drop pattern Phase 2 established. Confirmed by
direct row-count query that `users`/`tenants`/`tenant_members`/`refresh_tokens`
were untouched throughout.

**Industry templates & seed**: all 10 required templates (real estate,
clinic, hotel, restaurant, automotive, law firm, education, home services,
SaaS, custom) seeded via `backend/app/seed_data/industry_templates.py` +
`seed_runner.py`, idempotent (`(key, version)` upsert, never mutates an
existing row — verified by seeding twice and asserting zero duplicates
created the second time). Real estate, clinic, and hotel templates match
the exact qualification fields specified; clinic and law firm carry the
required mandatory safety language. A separate dev-only demo seed
(`seed_demo_data.py`) creates 3 fictional, clearly-labelled demo tenants
(Meridian Realty Group, Brightsmile Dental Clinic, The Wren Boutique Hotel),
each fully onboarded with a location/services/FAQ/knowledge document —
refuses to run outside `ENVIRONMENT=development`, prints one-time
credentials to the console only (never stored in any file).

**Business onboarding**: `GET /tenants/{id}/onboarding` computes progress
live from real stored data (no separate step-pointer to drift out of sync),
`PATCH .../business-profile`, `POST .../select-industry` (snapshots
template defaults into the tenant's own rows, only when untouched),
`POST .../complete-onboarding` (gated on business name + industry selection
+ a named receptionist).

**Receptionist & workflow**: full CRUD for `Receptionist`;
`ReceptionistWorkflow` created automatically alongside every receptionist.
Qualification schema/rules validated through `app/schemas/qualification.py`
(unique safe keys, supported types only, options required only for select
types, max 40 fields/30 options/40 rules, no expression language anywhere).
`enabled_actions` validated against a server allow-list of 11 actions
(configuration only — nothing executes). Clinic/law-firm mandatory safety
rules cannot be silently dropped on any workflow update — enforced
server-side on every write, not just at template selection.

**Locations & services**: working hours validated (day-of-week structure,
no overlapping intervals, closed days can't carry intervals, overnight
ranges explicitly rejected as an out-of-scope/documented limitation). At
most one primary location per tenant, enforced by both service-layer swap
logic and a DB-level partial unique index. `Service.location_id`, if
supplied, is explicitly re-validated to belong to the same tenant — a raw
FK alone doesn't know about tenant boundaries (a real gap found and fixed
during implementation, before it ever shipped).

**FAQs & manual knowledge**: FAQ CRUD with normalized-match duplicate
detection (warns, never blocks) and plain-text-only enforcement. Knowledge
is manual-only — `website`/`file_upload` source types exist as reserved
enum values the service layer explicitly rejects with a clear "not
supported yet" error. Chunking is deterministic (fixed 1000-character
windows, 100-character overlap, pure string slicing — no embeddings).
Search uses PostgreSQL full-text search (`to_tsvector`/`plainto_tsquery`/
`ts_rank`), always tenant-scoped first.

**Authorization**: owner/admin full read-write, member read-only,
non-member 404, unauthenticated 401 — identical model to Phase 2, applied
uniformly across every new resource type. The global industry-template
catalog is read-only for all authenticated users with no mutation route at
all (tested via an explicit `405` assertion, not just an assumption).

### A real bug found and fixed during Phase 3 testing (not a test bug)

The central `RequestValidationError` handler (`app/core/errors.py`, written
in Phase 1, never touched since) passed `exc.errors()` directly into a
plain `JSONResponse`. Any custom `@field_validator` raising a plain
`ValueError` — used throughout Phase 3 (unknown action, overlapping working
hours, HTML rejection, etc.) — produces a Pydantic error entry containing
the *raw exception object* in `ctx["error"]`, which `json.dumps` cannot
serialize; plain `JSONResponse` does not run its content through
`jsonable_encoder` the way FastAPI's own default handler does. The handler
itself crashed instead of returning a clean `422`. This went undetected
through Phases 1–2 because neither had a test that triggered a *custom*
validator's `ValueError` and asserted on the `422` response (built-in
Pydantic constraints like `Field(min_length=...)` don't hit this code path).
Fixed by wrapping `exc.errors()` in `jsonable_encoder(...)`. Also fixed
separately: `KnowledgeChunkRepository.search`'s original implementation
used raw `text()` clauses for the full-text-search rank column, which
SQLAlchemy 2.0 doesn't support `.label()`-ing directly (`NotImplementedError`)
— rewritten using `func.to_tsvector`/`func.plainto_tsquery`/`func.ts_rank`
and `.op("@@")`, which is also more idiomatic and keeps parameter binding
automatic rather than manual.

### Frontend

9 onboarding routes (`/onboarding/{business,industry,receptionist,locations,services,knowledge,qualification,actions,review}`)
sharing a `OnboardingProvider` context that redirects unauthenticated users
to `/login`, members straight to `/dashboard` (nothing for them to
configure), and already-completed tenants to `/dashboard` — plus 7 dashboard
settings pages under `/dashboard/settings/*` for post-onboarding editing.
Both surfaces render the *same* components (`src/components/settings/*`:
`BusinessProfileForm`, `IndustrySelector`, `ReceptionistForm`,
`LocationsManager`, `ServicesManager`, `FaqsManager`, `KnowledgeManager`,
`QualificationEditor`, `ActionsToggle`), per the reuse requirement. Progress
is fetched from the backend on every step navigation
(`GET /tenants/{id}/onboarding`) rather than tracked in client-only state,
so a refresh never loses or desyncs progress.

### Verification results (all passing)

- Backend: `pytest` **102/102** passed (industry templates, onboarding,
  receptionists/workflow incl. mandatory safety rules, locations incl.
  working-hours/primary-location edge cases, services incl. cross-tenant
  `location_id` validation, FAQs, knowledge incl. chunking/search/size
  limits, full authorization matrix, tenant isolation for every new
  resource at both HTTP and repository level), `ruff check` clean, `mypy`
  clean (84 source files)
- `alembic current` / `upgrade head` / `downgrade -1` / `upgrade head`: all
  verified against `ai_receptionist_dev`, no errors, Phase 2 tables
  confirmed untouched, connection string never printed
- Frontend: `eslint` clean, `tsc --noEmit` clean, `next build` succeeded —
  24 routes prerendered
- Widget: unchanged, still clean
- **Live 15-step end-to-end flow** (register → select industry → business
  profile → receptionist → location → service → FAQ → knowledge document →
  confirm search → customize qualification → configure actions → complete
  onboarding → reload config → non-member write rejected → cross-tenant
  access rejected) — all passed against the running backend + real
  database. Test data cleaned up afterward, confirmed by database name
  before deletion.

### Gap remediation round (complete)

Phase 3 was given provisional acceptance pending five gaps. All five are
closed:

**1. Select-field options editor** (`QualificationEditor.tsx`,
`qualification-utils.ts`): full add/edit/delete/reorder UI for
`single_select`/`multi_select` options, with client-side validation
(blank label/value, duplicate values, at least one option, `MAX_OPTIONS =
30`, `MAX_OPTION_LABEL_LENGTH`/`MAX_OPTION_VALUE_LENGTH = 100`) blocking
save with a visible `role="alert"` message before any request is sent.
Switching a field's type away from `single_select`/`multi_select` clears
its `options` safely. Options are plain-text only (HTML/script content
rejected, same as every other free-text field in this project). Backend
hardened to match: every qualification schema model now sets
`model_config = ConfigDict(extra="forbid")`, so an unsupported/unexpected
JSON structure is rejected with a clean `422` rather than silently
ignored. Covered by 15 new backend tests
(`backend/tests/test_qualification_schema.py`, including exact
save-and-reload preservation) and ~30 new frontend unit tests plus 6
component tests driving the real editor UI
(`qualification-utils.test.ts`, `QualificationEditor.test.tsx`).

**2. Revised onboarding completion rules**
(`backend/app/services/onboarding_service.py`): completion now requires a
valid business profile, a selected industry template, a named
receptionist, an **active** receptionist workflow
(`ReceptionistStatus.ACTIVE`), at least one enabled safe action, and at
least one active FAQ or active knowledge document. Locations and services
are deliberately **not** required — an online-only business needs
neither. `GET /tenants/{id}/onboarding` now returns a structured
`incomplete_requirements: [{code, message, step}]` list; a `complete-
onboarding` attempt that isn't ready returns a `422` with the same
structured list rather than a generic error, so the frontend can route
the user straight to the right step. **Product decision (documented, per
explicit instruction to choose and record the safer default): completion
is monotonic** — `complete_onboarding` is a no-op once a tenant is already
`COMPLETED`; it never reverts to `in_progress` if configuration later
regresses (e.g. the last enabled action gets disabled). A regression is
instead surfaced by continuing to populate `incomplete_requirements` even
post-completion, which the frontend renders as a non-blocking warning
banner (`onboarding-progress.ts`'s `summarizeRequirements` — `isWarning`
vs. `isBlocking`). Rationale: silently un-completing a tenant that already
has a live receptionist would be a more disruptive, more surprising
failure mode (e.g. re-triggering onboarding gates on an otherwise-working
account) than telling the owner "here's what's now missing" while leaving
the receptionist operative. Covered by 5 new/rewritten backend tests
covering incomplete-cannot-complete, missing-knowledge, missing/invalid-
workflow, missing-enabled-actions, valid-minimal-completion, and the
no-revert-on-regression behavior.

**3. Frontend test foundation**: Vitest + React Testing Library, zero
external services, `npm run test` / `npm run test:run`
(`frontend/vitest.config.ts`, `vitest.setup.ts`). One real setup bug found
and fixed during this work: RTL's automatic `afterEach(cleanup)` only
self-registers against Jest-style global test functions; this project
imports `describe`/`it`/`afterEach` explicitly from `vitest`, so without
wiring `cleanup()` explicitly in the setup file, DOM from one test leaked
into the next within the same file (visible as 6+ stacked copies of the
same component in the failing tests' DOM dumps). 59 tests total across 5
files: qualification option utilities and editor behavior, onboarding
progress/warning-summary computation, API error presentation
(`ApiError`, `errorMessage`, `getRequirementsFromError`), the
authentication/role/redirect logic gating onboarding routes
(`computeOnboardingRedirect`), and save-then-reload persistence of
qualification configuration through a mocked backend.

**4. Re-verification**: see "Verification results" below — everything is
green, including a live end-to-end corrective flow.

**5. Security/repository review**: no credentials or `.env` files tracked
(`git status` clean of anything beyond source), no test/coverage output,
`node_modules`, or build artifacts staged, no cross-tenant behavior
touched, clinic/law-firm mandatory safety-rule enforcement untouched,
industry-template catalog still immutable to tenant users (unchanged
code path), no Phase 4 AI/conversation code added.

**Two more real bugs found (not test bugs) while re-verifying end-to-end:**

- **`onboarding/review/page.tsx` showed a stale "before you can complete"
  requirement list after fixing it on another page.** The component
  seeded its local `requirements` state from `state?.incomplete_
  requirements` via a bare `useState(...)` initializer. `useState`
  initializers run exactly once per mount; if the onboarding context's own
  background refresh hadn't resolved yet at that exact render (a very
  achievable race after navigating from another step), the stale snapshot
  froze permanently — later context updates (e.g. the step tracker, which
  reads `state` directly every render) kept moving, but this list didn't,
  even though the backend had already returned `incomplete_requirements:
  []`. Reproduced live: added an FAQ, returned to Review, saw the step
  tracker correctly mark Knowledge complete while the blocking banner
  still listed "add an active FAQ." Fixed by only ever populating that
  local state from a *failed completion attempt's* response, and deriving
  the steady-state list directly from the live context value instead of a
  one-time snapshot.
- **Registration's default timezone value is rejected by the backend.**
  `/register`'s timezone `<select>` defaults to the browser-supplied
  `Asia/Calcutta`, which the backend's IANA timezone validator rejects
  (`Unknown IANA timezone: 'Asia/Calcutta'` — likely a tzdata link-name
  mismatch; the canonical modern name is `Asia/Kolkata`). This is
  pre-existing Phase 1/2 registration-form behavior, not something this
  remediation round touched, and is **documented here, not fixed**, since
  it's outside the five approved gaps. Worked around for the live
  end-to-end test by selecting a different timezone. Recommend fixing in
  a small follow-up: either default the `<select>` to a value already
  known-valid to the backend, or validate/normalize IANA aliases
  server-side.

**One config gap fixed in passing**: `ruff check .` (unscoped) was
linting Alembic's auto-generated `alembic/versions/*.py` files, which are
tool-generated and were never meant to be held to the `app`/`tests` style
rules — `pyproject.toml`'s `src = ["app", "tests"]` already signaled that
intent but nothing enforced it. Added `extend-exclude =
["alembic/versions"]`. Separately, `alembic/env.py` (hand-written, not
autogenerated) had a genuine unsorted-import finding, fixed via `ruff
--fix` (import reordering only, no behavior change) and re-verified with
`alembic current`/`alembic check` and the full pytest suite afterward.

### Verification results (gap remediation — all passing)

- Backend: `pytest` **121/121** passed, `ruff check` clean, `mypy` clean
  (84 source files), `alembic current` shows a single head with no drift
  (`alembic check`: "No new upgrade operations detected") — no migration
  history was rewritten, only `pyproject.toml`'s ruff scope and one
  hand-written `env.py` import order changed
- Frontend: `npx vitest run` **59/59** passed, `eslint` clean, `tsc
  --noEmit` clean, `next build` succeeded (24 routes prerendered)
- Widget: unchanged this round — `eslint`, `tsc --noEmit`, and `tsc`
  build all still clean
- **Live end-to-end corrective flow**, run against the real backend +
  database with a fresh tenant (`register` → `industry: Custom/Other
  Business` → receptionist set to `Active` status → added a
  `single_select` "Service tier" qualification field with two options,
  Basic/basic and Premium/premium → **saved, reloaded the page, confirmed
  exact preservation** via direct DOM inspection → attempted a third
  option with a duplicate value → **confirmed rejection**: the client-side
  validation alert fired and no `PATCH .../workflow` request was ever sent
  → attempted "Complete onboarding" with no FAQ/knowledge yet →
  **confirmed the backend reports `ready_to_complete: false` with
  `incomplete_requirements` containing `knowledge_or_faq`**, and the
  frontend correctly refused to call the completion endpoint → added an
  active FAQ → returned to Review → **confirmed the requirement cleared**
  (after the stale-state bug above was found and fixed) →
  **completed onboarding successfully** (`onboarding_status: "completed"`
  confirmed via the actual `POST .../complete-onboarding` response) → logged
  out and back in fresh → **confirmed the completed qualification
  configuration, including the select field's two options, reloaded
  byte-for-byte identical** from the settings page. Test tenant left in
  place in the local dev database (not production data; no cleanup
  requested for this round, unlike prior phases' live-flow tests — flag if
  cleanup is wanted).

### Known limitations / carried forward

- Overnight working hours are explicitly unsupported (documented, tested,
  rejected with a clear error rather than mishandled).
- ~~The `/register` page's default timezone value (`Asia/Calcutta`) is
  rejected by the backend's IANA validator~~ — **fixed**, see "Timezone
  remediation round" below.
- Invitation delivery, expired-refresh-token cleanup job, Docker
  runtime-testing, and the frontend `postcss` advisory all carried forward
  unchanged from Phase 1/2.

### Timezone remediation round (complete)

**Root cause**: the frontend populated every timezone `<select>` from
`Intl.supportedValuesOf('timeZone')` (418 entries in this browser) and
auto-selected the browser's *detected* zone via
`Intl.DateTimeFormat().resolvedOptions().timeZone`. The backend validates
every `timezone` field against Python's `zoneinfo.available_timezones()`
(498 entries on this system). These are two independently-maintained
"IANA timezone truth" sources that disagree about which legacy
backward-compatibility link names are still valid: a systematic audit
(diffing the two sets) found **18 names** the browser would happily offer
or auto-select that the backend rejects outright — not just the one
reported (`Asia/Calcutta`, whose canonical form is `Asia/Kolkata`), but
also `Africa/Asmera`, `America/Buenos_Aires`, `America/Catamarca`,
`America/Cordoba`, `America/Godthab`, `America/Indianapolis`,
`America/Jujuy`, `America/Louisville`, `America/Mendoza`,
`Asia/Katmandu`, `Asia/Rangoon`, `Asia/Saigon`, `Atlantic/Faeroe`,
`Europe/Kiev`, `Pacific/Enderbury`, `Pacific/Ponape`, and `Pacific/Truk`.
Confirmed that neither runtime's `Intl.DateTimeFormat` canonicalizes
these aliases to a form the other accepts — Chromium's ICU echoes the
alias back unchanged (`Intl.DateTimeFormat(undefined, {timeZone:
"Asia/Calcutta"}).resolvedOptions().timeZone === "Asia/Calcutta"`), so a
purely client-side canonicalization pass cannot close the gap; the two
tzdata builds' notion of "canonical" genuinely differ.

**Fix — backend becomes the single source of truth**:
- New `app/core/timezones.py`: `VALID_TIMEZONES` (a `frozenset`) and
  `SORTED_TIMEZONES`, replacing four independent
  `zoneinfo.available_timezones()` calls previously duplicated across
  `schemas/auth.py`, `schemas/business_profile.py`,
  `schemas/business_location.py`, and `schemas/tenant.py`. All four now
  import from this one place — no behavior change, one less place for the
  four to silently drift apart.
- New public, unauthenticated `GET /api/v1/timezones` endpoint
  (`app/api/v1/timezones.py`) returning `SORTED_TIMEZONES` — needed
  unauthenticated because the registration form loads before any session
  exists (same pattern as `/health`). Backend validators were **not**
  relaxed to accept more names; the fix moves the frontend onto the
  backend's existing valid set rather than moving the backend's valid set
  toward the frontend's.
- Frontend `lib/timezones.ts` rewritten: `fetchSupportedTimezones()` +
  `useTimezoneOptions()` hook fetch this endpoint (falling back to
  `["UTC"]` if the request fails, so a picker is never empty or broken);
  every timezone `<select>` (`/register`, `BusinessProfileForm`) now
  renders from this backend-sourced list instead of
  `Intl.supportedValuesOf`. A small, explicitly-scoped
  `KNOWN_BROWSER_TIMEZONE_ALIASES` map (the 18 names above → their modern
  canonical form) plus `resolveDefaultTimezone()` normalize the *detected*
  browser default before selecting it — but this map is a UX nicety, not
  a validity list: an alias missing from the map just falls back to
  `"UTC"` (a real, always-accepted zone) rather than guessing wrong or
  submitting something unvalidated. `/register`'s default now resolves to
  `Asia/Kolkata` for a browser reporting `Asia/Calcutta`, and to `UTC`
  for any detected zone the map and the backend both don't recognize.

**Tests added** (8 backend, 13 frontend):
- `backend/tests/test_timezones.py`: the `/timezones` endpoint is public
  and returns only backend-valid names (asserted against
  `zoneinfo.available_timezones()` directly) while excluding known legacy
  aliases; registration accepts `Asia/Kolkata` and `UTC`; registration
  **rejects** `Asia/Calcutta` and an arbitrary invalid string with `422`
  (confirming the backend still never silently accepts an invalid
  timezone); a sampled round-trip test registers with ~25 evenly-spaced
  entries from the endpoint's own list and asserts every one is accepted.
- `frontend/src/lib/timezones.test.ts`: `normalizeTimezoneAlias` maps
  `Asia/Calcutta` → `Asia/Kolkata` and the other 17 known aliases
  correctly, passes through canonical/unrecognized names unchanged, and
  never chains one alias to another; `resolveDefaultTimezone` normalizes-
  then-selects when the canonical form is supported, uses an
  already-canonical detected zone as-is, and falls back to `UTC` both
  when the (normalized) detected zone isn't in the supplied list and when
  detection itself throws; `useTimezoneOptions` populates from a mocked
  backend response and keeps the `UTC` fallback on a failed fetch.

**Live India-default registration test** (item 10 — no manual dropdown
change): patched `Intl.DateTimeFormat` in a real browser tab to report
`Asia/Calcutta` (the exact original bug scenario), then loaded `/register`
fresh so the patched detection ran through the real component code path.
The Time Zone `<select>` auto-selected **`Asia/Kolkata`** with all 498
backend-valid options loaded — confirmed both via a DOM screenshot and by
reading the live `<select>` element's value. Filled name/email/password/
workspace fields, submitted **without touching the timezone field**:
`POST /api/v1/auth/register` → `201 Created`. Verified directly against
the database that the created tenant's `timezone` column stored exactly
`Asia/Kolkata` — not the browser's original `Asia/Calcutta`, not a silent
`UTC` fallback. Test tenant, membership, and user cleaned up afterward.

### Verification results (timezone remediation — all passing)

- Backend: `pytest` **129/129** passed (121 + 8 new), `ruff check` clean,
  `mypy` clean (87 source files), `alembic current`/`alembic check`: single
  head, "No new upgrade operations detected" — no schema change was
  needed (this fix is application-code + one new read-only route, not a
  data model change)
- Frontend: `npx vitest run` **72/72** passed (59 + 13 new), `eslint`
  clean, `tsc --noEmit` clean, `next build` succeeded (24 routes
  prerendered)
- Widget: unaffected — `eslint`, `tsc --noEmit`, and `tsc` build all still
  clean
- **Live India-default registration flow** — see above — passed
  end-to-end against the real backend + database, with database-level
  confirmation of the stored value.

## Upcoming — Phase 4 (not started)

AI provider abstraction (development mock, OpenAI, Anthropic), conversation
orchestration, streaming, and controlled backend tools. Awaiting approval
before starting.

Industry templates, business settings, and knowledge/FAQ management.
Awaiting approval before starting.
