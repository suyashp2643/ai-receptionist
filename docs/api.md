# API Reference (Phase 3)

Base path: `/api/v1`. Full interactive docs at `/docs` (Swagger UI) when the
backend is running. See `docs/security.md` for the auth/CSRF model these
routes rely on.

## Health

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/health` | none | Also mounted here, identical to below |
| GET | `/api/v1/health` | none | Reports `status`, `service`, `environment`, `database.{status,detail}` |

## Timezones

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/api/v1/timezones` | none | `{ "timezones": ["Africa/Abidjan", ..., "UTC"] }` |

Public and unauthenticated — the registration form needs a backend-valid
timezone list before any session exists. Returns the exact same
`zoneinfo.available_timezones()` set every `timezone` field is validated
against (see `docs/database-schema.md`'s "Timezone validation" section),
sorted alphabetically. The frontend populates every timezone `<select>`
from this endpoint rather than the browser's own
`Intl.supportedValuesOf('timeZone')`, which includes legacy IANA
"backward"-compatibility link names (e.g. `Asia/Calcutta`, `Europe/Kiev`)
that this backend's tzdata build does not accept — anything rendered from
this endpoint is guaranteed to pass every `timezone` validator below.

## Auth

| Method | Path | Auth | CSRF required |
|---|---|---|---|
| POST | `/api/v1/auth/register` | none | no |
| POST | `/api/v1/auth/login` | none | no |
| POST | `/api/v1/auth/refresh` | refresh cookie | **yes** |
| POST | `/api/v1/auth/logout` | refresh cookie (optional) | **yes** |
| GET | `/api/v1/auth/me` | Bearer access token | no |

**`POST /api/v1/auth/register`**
```json
// request
{
  "display_name": "Ada Lovelace",
  "email": "ada@example.com",
  "password": "at least 8 characters, up to 256",
  "workspace_name": "Ada's Workspace",
  "timezone": "Europe/London"
}
// response 201 — sets refresh + CSRF cookies
{
  "access_token": "...",
  "token_type": "bearer",
  "expires_in": 900,
  "user": { "id": "...", "normalized_email": "ada@example.com", "display_name": "Ada Lovelace", "is_active": true, "last_login_at": null, "created_at": "..." },
  "memberships": [ { "tenant_id": "...", "tenant_name": "Ada's Workspace", "tenant_slug": "adas-workspace-a1b2c3", "role": "owner", "status": "active" } ]
}
```
`409` if the normalized email is already registered. `422` for password
length / invalid email / unknown timezone (see "Timezones" above for how
the frontend avoids ever submitting one).

**`POST /api/v1/auth/login`** — `{ "email": ..., "password": ... }` → same
`TokenResponse` shape as register. `401 Invalid email or password.` for any
failure (unknown email, wrong password, inactive account) — deliberately
indistinguishable.

**`POST /api/v1/auth/refresh`** — no body; reads the refresh cookie,
requires `X-CSRF-Token` header matching the CSRF cookie. Returns a fresh
`TokenResponse` and rotates both cookies. `401` if the refresh token is
missing/invalid/expired/reused; `403` if the CSRF header is missing or
doesn't match.

**`POST /api/v1/auth/logout`** — no body; same CSRF requirement. `204 No
Content`. Always clears both cookies, even if no valid session was found.

**`GET /api/v1/auth/me`** — `Authorization: Bearer <access_token>` required.
Returns `{ user, memberships }`.

## Tenants

| Method | Path | Minimum role |
|---|---|---|
| POST | `/api/v1/tenants` | any authenticated user (becomes owner of the new tenant) |
| GET | `/api/v1/tenants` | any authenticated user (lists only their own memberships) |
| GET | `/api/v1/tenants/{tenant_id}` | any active member |
| PATCH | `/api/v1/tenants/{tenant_id}` | `admin` |
| GET | `/api/v1/tenants/{tenant_id}/members` | `admin` |

All `{tenant_id}` routes: `404` if the caller has no active membership in
that tenant (existence is not confirmed either way); `403` if they are a
member but below the required role.

**`POST /api/v1/tenants`** — `{ "name": "...", "timezone": "UTC" }` → `201`,
`TenantRead` with `my_role: "owner"`.

**`GET /api/v1/tenants`** → list of `TenantMembershipSummary` (same shape as
`memberships` in auth responses), scoped to the caller.

**`GET /api/v1/tenants/{tenant_id}`** → `TenantRead`:
```json
{ "id": "...", "name": "...", "slug": "...", "timezone": "UTC", "status": "active", "created_at": "...", "my_role": "owner" }
```

**`PATCH /api/v1/tenants/{tenant_id}`** — partial update, `{ "name"?: ..., "timezone"?: ... }` → updated `TenantRead`. A `role`/`my_role` field in the
body has no effect — role is never accepted from the client.

**`GET /api/v1/tenants/{tenant_id}/members`** → list of `TenantMemberRead`:
```json
[{ "id": "...", "user_id": "...", "display_name": "...", "normalized_email": "...", "role": "owner", "status": "active", "created_at": "..." }]
```

## Industry templates (global catalog)

| Method | Path | Auth |
|---|---|---|
| GET | `/api/v1/industry-templates` | any authenticated user |
| GET | `/api/v1/industry-templates/{key}` | any authenticated user |

Read-only for everyone — there is no route to create/update/delete a
template (verified by a test asserting `405` on `POST`/`PATCH`). Returns the
**latest active version** of each template. `GET .../{key}` → `404` for an
unknown or inactive key.

## Onboarding & business profile

| Method | Path | Minimum role |
|---|---|---|
| GET | `/api/v1/tenants/{tenant_id}/onboarding` | any active member |
| PATCH | `/api/v1/tenants/{tenant_id}/business-profile` | `admin` |
| POST | `/api/v1/tenants/{tenant_id}/select-industry` | `admin` |
| POST | `/api/v1/tenants/{tenant_id}/complete-onboarding` | `admin` |

**`GET .../onboarding`** — progress is *computed live from real data*, never
a separate stored pointer:
```json
{
  "status": "in_progress",
  "completed_at": null,
  "ready_to_complete": false,
  "steps": {
    "business_profile": true, "industry_selected": true, "receptionist": false,
    "locations": false, "services": false, "knowledge": false,
    "qualification": false, "actions": false
  },
  "incomplete_requirements": [
    { "code": "receptionist_named", "message": "Give your receptionist a name.", "step": "receptionist" },
    { "code": "knowledge_or_faq", "message": "Add at least one active FAQ or active knowledge document.", "step": "knowledge" }
  ],
  "business_profile": { "...": "BusinessProfileRead" }
}
```
`incomplete_requirements` is the single source of truth the frontend uses
to route a user to the correct step — `steps` is presentation-only progress
(used for the "N of 8 complete" tracker), `incomplete_requirements` is what
actually gates completion. `locations` and `services` are tracked in
`steps` but are **never** part of `incomplete_requirements` — a business
with no physical location or bookable service can still complete
onboarding.

**`POST .../select-industry`** — `{ "template_key": "clinic" }`. Creates the
tenant's first `Receptionist` + `ReceptionistWorkflow` if none exists yet,
and snapshots the template's current defaults into them — **only if the
workflow still looks untouched** (no qualification fields, no enabled
actions yet), so re-selecting or switching templates never clobbers real
customization. `422` for an unknown/inactive `template_key`.

**`POST .../complete-onboarding`** — requires all of: a business profile
with `business_name` set, a selected industry template, a named
receptionist, that receptionist's workflow being active
(`Receptionist.status == "active"`), at least one enabled safe action on
the workflow, and at least one active FAQ or active knowledge document.
Locations and services are **not** required. If any requirement is unmet,
returns `422`:
```json
{
  "error": {
    "message": "Onboarding requirements are not met yet.",
    "status_code": 422,
    "requirements": [
      { "code": "workflow_active", "message": "Set your receptionist's status to Active.", "step": "receptionist" }
    ]
  }
}
```
**Completion is monotonic**: once `onboarding_status` is `completed`, this
endpoint is a no-op that returns the current profile unchanged — it never
reverts a tenant back to `in_progress` even if configuration later
regresses (e.g. the last enabled action gets disabled, or the active FAQ
is deactivated). A regression instead continues to appear in
`GET .../onboarding`'s `incomplete_requirements`, which the frontend
renders as a non-blocking warning rather than as something that blocks
further use of an already-live receptionist.

## Receptionists

| Method | Path | Minimum role |
|---|---|---|
| GET, POST | `/api/v1/tenants/{tenant_id}/receptionists` | member (GET) / `admin` (POST) |
| GET, PATCH | `/api/v1/tenants/{tenant_id}/receptionists/{id}` | member (GET) / `admin` (PATCH) |
| GET, PATCH | `/api/v1/tenants/{tenant_id}/receptionists/{id}/workflow` | member (GET) / `admin` (PATCH) |

Creating a receptionist always creates its `ReceptionistWorkflow` in the
same call — `GET .../workflow` never 404s for a receptionist that exists.

**`PATCH .../workflow`** body (all optional, partial update):
```json
{
  "qualification_schema": { "fields": [ { "key": "budget_max", "label": "Max budget", "type": "currency", "required": false, "display_order": 0, "is_sensitive": false } ] },
  "enabled_actions": ["answer_questions", "capture_contact"],
  "safety_rules": ["..."]
}
```
`enabled_actions` values must all be in the server allow-list (`422`
otherwise). If the receptionist's industry template is `clinic` or
`law_firm`, `safety_rules` must still include every mandatory rule for that
template — omitting one returns `422` naming which rule(s) are missing (see
`docs/security.md`).

## Locations

| Method | Path | Minimum role |
|---|---|---|
| GET, POST | `/api/v1/tenants/{tenant_id}/locations` | member (GET) / `admin` (POST) |
| GET, PATCH, DELETE | `/api/v1/tenants/{tenant_id}/locations/{id}` | member (GET) / `admin` (PATCH/DELETE) |

`working_hours` shape: `{ "days": [ { "day_of_week": 0, "closed": false, "intervals": [ { "start": "09:00", "end": "17:00" } ] } ] }`
(`day_of_week`: 0=Monday..6=Sunday). Overlapping intervals within a day, a
closed day with intervals, or an overnight interval (`end <= start`) all
return `422`. Setting `is_primary: true` automatically unsets any other
primary location for the tenant — a `422` cannot happen from a race here (a
partial unique index backstops it at the DB level).

## Services

| Method | Path | Minimum role |
|---|---|---|
| GET, POST | `/api/v1/tenants/{tenant_id}/services` | member (GET) / `admin` (POST) |
| GET, PATCH, DELETE | `/api/v1/tenants/{tenant_id}/services/{id}` | member (GET) / `admin` (PATCH/DELETE) |

`location_id`, if provided, must reference a location belonging to the
*same* tenant — `422 Unknown location_id` otherwise, even if the ID is a
real location belonging to a different tenant. `currency` must be a
3-letter code (normalized to uppercase). Descriptive only — no payments, no
availability.

## FAQs

| Method | Path | Minimum role |
|---|---|---|
| GET, POST | `/api/v1/tenants/{tenant_id}/faqs` | member (GET) / `admin` (POST) |
| GET, PATCH, DELETE | `/api/v1/tenants/{tenant_id}/faqs/{id}` | member (GET) / `admin` (PATCH/DELETE) |

`POST` response wraps the created FAQ: `{ "faq": {...}, "possible_duplicate_of": "<uuid-or-null>" }`
— a normalized-match duplicate is flagged, never blocked. `question`/`answer`
reject any `<`/`>` character (plain text only) and are length-capped
(500 / 5000 chars).

## Knowledge (manual only in Phase 3)

| Method | Path | Minimum role |
|---|---|---|
| GET, POST | `/api/v1/tenants/{tenant_id}/knowledge/sources` | member (GET) / `admin` (POST) |
| GET, POST | `/api/v1/tenants/{tenant_id}/knowledge/documents` | member (GET) / `admin` (POST) |
| GET, PATCH, DELETE | `/api/v1/tenants/{tenant_id}/knowledge/documents/{id}` | member (GET) / `admin` (PATCH/DELETE) |
| POST | `/api/v1/tenants/{tenant_id}/knowledge/search` | any active member |

`POST .../sources` with `type: "website"` or `"file_upload"` → `422` (not
implemented yet — reserved enum values only). `POST .../documents` chunks
`raw_text` deterministically on creation; `DELETE` removes the document and
all its chunks. `POST .../search` body `{ "query": "..." }` → PostgreSQL
full-text search, always scoped to the caller's tenant, never leaking
another tenant's content.

## Error shape

Every error response (from `app/core/errors.py`) has the same shape:
```json
{ "error": { "message": "...", "status_code": 404 } }
```
(422 validation errors additionally include `"details": [...]` — the
Pydantic error list, safely JSON-encoded via `jsonable_encoder`.)

## Not implemented in Phase 3

AI providers, LLM calls, conversation orchestration, streaming, chat
messages, embeddings, website crawling, document parsing, voice, the public
widget, appointment execution, analytics, and any Revenue Brain / AI Sales
Employee integration — all later, explicitly-approved phases.
