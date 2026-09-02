# API Reference (Phase 4)

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

## Test conversations (Phase 4)

Private and authenticated only — there is no public/unauthenticated
conversation endpoint, and none of these routes require CSRF (they're all
Bearer-token authenticated, not cookie-authenticated, matching every other
tenant-scoped route). Minimum role is `member` throughout: running a private
test conversation doesn't modify receptionist configuration, so the same
read-permission tier that can already view a receptionist's settings can
drive one.

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/tenants/{tenant_id}/receptionists/{receptionist_id}/test-conversations` | Starts a conversation. `404` if the receptionist doesn't exist or belongs to another tenant. |
| GET | `/api/v1/tenants/{tenant_id}/test-conversations` | Paginated list (`limit`/`offset`, capped at 50), optional `?receptionist_id=` filter. |
| GET | `/api/v1/tenants/{tenant_id}/test-conversations/{id}` | Conversation + paginated messages + summary (`null` until completed). |
| POST | `/api/v1/tenants/{tenant_id}/test-conversations/{id}/messages` | The conversation turn — see SSE contract below. Body: `{ "content": "...", "idempotency_key": "<optional>" }`. |
| POST | `/api/v1/tenants/{tenant_id}/test-conversations/{id}/complete` | Marks the conversation completed and generates its summary. `409` if already completed/abandoned. |

There is deliberately no separate `GET .../stream` route and no `.../retry`
route: the SSE stream *is* the direct response of `POST .../messages`, and
retry is just resubmitting that same call with the same `idempotency_key`
(the second call replays the stored result rather than reprocessing, so a
retry can never produce a different qualification outcome than the first
attempt got).

### SSE event contract

`POST .../messages` returns `text/event-stream`. Events, in emission order:

| Event | When | Payload |
|---|---|---|
| `message.started` | Immediately after the user message is persisted | `conversation_id`, `user_message_id`, `sequence_number` |
| `retrieval.completed` | After grounding search runs (skipped, `count: 0`, if a safety response will be used instead) | `count`, `sources: [{source_id, source_type, title, score}]` |
| `tool.started` | Before executing an allow-listed tool call | `tool_name`, `call_id` |
| `tool.completed` | After that tool call returns | `tool_name`, `call_id`, `status` |
| `response.delta` | Once per streamed chunk of the final answer | `delta` |
| `response.completed` | Once, after the assistant message is persisted | `message_id`, `sequence_number`, `content`, `citations`, `safety_labels` |
| `conversation.updated` | Always last on success | `collected_data`, `missing_required_fields`, `qualification_complete`, `status` |
| `response.error` | In place of `response.completed`/`conversation.updated` on a provider failure | `code`, `message` (never a raw exception, stack trace, or provider error string) |

A `response.error` event means the turn did **not** complete — the client
must not treat it as if `conversation.updated` had been received, and the
persisted conversation state on a subsequent `GET` will agree (no
partial/phantom completion). `message_id` and every other identifier in
these events is always a real, already-persisted UUID string — never a
placeholder.

### Qualification, safety, and tools surfaced by these events

- `missing_required_fields` / `collected_data` (from `conversation.updated`)
  drive the test console's qualification panel. A rejected/invalid select
  value is never written to `collected_data` — it stays in
  `missing_required_fields` and the next turn's `response.delta` explains
  why.
- `safety_labels` on `response.completed` is non-empty exactly when that
  turn's reply came from the deterministic safety engine
  (`app/ai/safety.py`), not the provider — see docs/security.md.
- `tool.started`/`tool.completed` only ever name one of the four
  server-registered, allow-listed tools (`search_business_knowledge`,
  `list_services`, `get_business_hours`, `get_business_profile`) — no
  write-action tool exists or can be invoked in Phase 4.

## Error shape

Every error response (from `app/core/errors.py`) has the same shape:
```json
{ "error": { "message": "...", "status_code": 404 } }
```
(422 validation errors additionally include `"details": [...]` — the
Pydantic error list, safely JSON-encoded via `jsonable_encoder`.)

## Not implemented in Phase 4

The public embeddable widget conversation endpoint, browser voice, telephone
calling, WhatsApp/SMS, live/public (unauthenticated) conversations, actual
appointment/lead/handoff execution, CRM integrations, billing, production
analytics, and any Revenue Brain / AI Sales Employee integration — all
later, explicitly-approved phases. A real (non-mock) provider's HTTP calls,
embeddings, website crawling, document parsing, and voice are likewise still
out of scope.
