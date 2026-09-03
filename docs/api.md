# API Reference (Phase 5)

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

The public widget's appointment form has no equivalent backend-sourced
picker to sidestep this with (see its own section below) — it falls back to
the visitor's raw browser-detected timezone when no location is selected,
so the appointment-request endpoint instead normalizes a short, explicit
list of known legacy aliases (`app/core/timezones.py`'s
`LEGACY_TIMEZONE_ALIASES`) before validating, catching the same class of
value (e.g. `Asia/Calcutta` → `Asia/Kolkata`) this endpoint's own consumers
avoid by construction.

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

## Widget installation management (dashboard, authenticated) (Phase 5)

| Method | Path | Minimum role |
|---|---|---|
| GET, POST | `/api/v1/tenants/{tenant_id}/widget-installations` | member (GET) / `admin` (POST) |
| GET, PATCH | `/api/v1/tenants/{tenant_id}/widget-installations/{id}` | member (GET) / `admin` (PATCH) |
| GET | `/api/v1/tenants/{tenant_id}/widget-installations/{id}/embed-snippet` | member |
| POST | `/api/v1/tenants/{tenant_id}/widget-installations/{id}/activate` | `admin` |
| POST | `/api/v1/tenants/{tenant_id}/widget-installations/{id}/pause` | `admin` |
| POST | `/api/v1/tenants/{tenant_id}/widget-installations/{id}/revoke` | `admin` |

**`POST .../widget-installations`** — `{ "receptionist_id": "...", "allowed_domains": ["example.com"] }`.
Starts in `status: "draft"` (serves no public traffic until activated).
`allowed_domains` are normalized bare hostnames — no scheme/path/port,
no wildcards, `localhost` only when the backend's `ENVIRONMENT=development`
(`422` otherwise); see `docs/security.md`'s domain-validation section.
`receptionist_id` must belong to the same tenant (`404` otherwise).

**`GET .../embed-snippet`** — returns the installation fields plus
`embed_snippet` (the literal `<script>` tag to paste) and `widget_bundle_url`
(`Settings.widget_bundle_url`, a local dev URL by default — Phase 5 does not
claim production widget-bundle hosting exists).

**Revocation is terminal**: `POST .../revoke` cannot be undone via
`activate` (`409`) — a tenant that wants the widget back creates a new
installation, which mints a new `public_id`. This is deliberate: the old
`public_id` may already be cached or scraped from a page's source, so
reviving it would silently un-revoke something a tenant explicitly turned
off.

**Live local preview** (`/dashboard/receptionist/widget`, no separate REST
endpoint of its own — it composes the routes above with the public widget
API): renders `frontend/public/widget-preview.html` in a sandboxed iframe,
using `embed-snippet`'s real `widget_bundle_url` and the installation's real
`public_id` — the actual production widget bundle against the actual public
API, not a mock or a separate code path. See docs/architecture.md for the
full design (platform preview origin trust, capability-token flow, preview
traffic tagging, and why no dashboard credential ever reaches it).

## Widget records — minimal verification views (dashboard, authenticated) (Phase 5)

| Method | Path | Minimum role |
|---|---|---|
| GET | `/api/v1/tenants/{tenant_id}/widget-records/contacts` | member |
| GET | `/api/v1/tenants/{tenant_id}/widget-records/enquiries` | member |
| GET | `/api/v1/tenants/{tenant_id}/widget-records/appointment-requests` | member |
| GET | `/api/v1/tenants/{tenant_id}/widget-records/handoff-requests` | member |

Read-only, paginated (`limit`/`offset`, default 50, capped at 200), newest
first. This is deliberately **not** the full Phase 6 analytics dashboard —
just enough to verify that a widget conversation's captured contact,
enquiry, appointment request, or handoff request actually landed in the
tenant's own records.

## Public widget API (unauthenticated beyond a capability token) (Phase 5)

Base path: `/api/v1/widget/{public_id}`. No dashboard JWT is ever required
or accepted here. `public_id` is `WidgetInstallation.public_id` — public and
non-secret by design (see `docs/security.md`'s threat model for the full
security model this section assumes). CORS for this path is handled by a
separate, non-credentialed policy (`app/core/widget_cors.py`) — see
`docs/security.md`.

| Method | Path | Requires capability token |
|---|---|---|
| GET | `.../config` | no |
| POST | `.../sessions` | no (this is what issues one) |
| POST | `.../conversations` | yes (an *existing* token, to start an additional conversation) |
| GET | `.../conversations/{conversation_id}` | yes |
| POST | `.../conversations/{conversation_id}/messages` | yes |
| POST | `.../contacts` | yes |
| POST | `.../appointment-requests` | yes |
| POST | `.../handoff-requests` | yes |

A capability token is presented via the `X-Widget-Session-Token` header
(never a cookie, never a query parameter). `/contacts`,
`/appointment-requests`, and `/handoff-requests` take no `conversation_id`
in the path — the token alone determines the conversation, since a
`WidgetVisitorSession` is always scoped 1:1 to exactly one conversation.

**`GET .../config`** → `WidgetConfigRead` — every field is explicitly
public-safe (business name, receptionist name, welcome message, suggested
questions, logo/accent color, supported languages, voice availability,
theme, launcher position, AI disclosure, privacy notice, `mock_mode: true`,
safe business contact email/phone, installation `status` so a
paused/draft widget can render an accurate "unavailable" state, and —
added after initial Phase 5 review — `services`/`locations`, each an array
of **active-only** records with only `id`/`name`/`description` (services)
or `id`/`name`/`timezone` (locations); an empty array when none are
configured, so the widget only renders a picker when there's something to
pick). Never includes a tenant or receptionist UUID, system prompt, private
knowledge content, credentials, service pricing/category, or any other
tenant's data. `404` for an unknown or **revoked** `public_id` (revoked
behaves exactly like "never existed" — it does not confirm the `public_id`
once worked). Origin is validated here too (see `docs/security.md`) but a
missing Origin is let through; the dashboard's own origin
(`PLATFORM_PREVIEW_ORIGINS`) is always allowed, for the live preview
feature, regardless of a tenant's configured `allowed_domains`.

**`POST .../sessions`** — body `{ "visitor_reference"?: "...", "locale"?: "en" }`
(same shape as the dashboard's `StartConversationRequest` — no
widget-specific fields needed). Requires the installation to be `active`
(`409` for draft/paused/revoked — draft/paused still serve `GET .../config`,
just not this). Starts a new `Conversation` with
`mode="widget", channel="widget"` (additive enum values — Phase 4's
dashboard test-console conversations still default to `mode="test",
channel="dashboard_test"`, unaffected) and a `WidgetVisitorSession`.
Response:
```json
{
  "capability_token": "<raw token — shown exactly once>",
  "expires_at": "2026-01-02T00:00:00Z",
  "conversation": { "id": "...", "status": "active", "locale": "en", "qualification_complete": false, "started_at": "...", "last_message_at": null }
}
```
Note `conversation` here is `WidgetConversationRead` — it never includes
`tenant_id` or `receptionist_id`, unlike the dashboard's `ConversationRead`.

**`POST .../conversations`** — same body and response shape as `/sessions`,
but requires an existing, still-valid capability token from this same
installation (header, not body) as proof the caller already completed the
domain-gated `/sessions` handshake once. This is the "start a new
conversation" action from within an already-open widget (the transcript's
"＋" button), not a general-purpose unauthenticated conversation factory —
it mints a brand-new conversation and token, independent of the one
presented.

**`GET .../conversations/{conversation_id}`** → `{ conversation, messages }`,
`messages` filtered to `user`/`assistant` roles only (tool-call audit rows
are never serialized here). `401` for a missing/invalid/expired/revoked
token or one scoped to a different conversation — the same generic message
in every case (see `docs/security.md`).

**`POST .../conversations/{conversation_id}/messages`** — identical SSE
contract to the dashboard's `POST .../test-conversations/{id}/messages`
(see that section above) — reuses the same `ConversationOrchestrator` and
streaming adapter unchanged. `409` if the conversation is not active, or if
it has reached `Settings.widget_max_messages_per_conversation` (default
200). Rate-limited separately from session creation (see
`docs/security.md`).

**`POST .../contacts`** — body: `{ "name"?, "email"?, "phone"?, "preferred_contact_method"?: "email"|"phone"|"either", "marketing_consent"?: false }`.
`422` if none of name/email/phone is provided. Response:
`{ "status": "received", "contact_id": "...", "marketing_consent": false }`
— identical shape whether or not this matched an existing contact (see
`docs/security.md`'s consent section).

**`POST .../appointment-requests`** — body:
```json
{
  "requested_date": "2026-03-01",
  "requested_time"?: "14:00:00",
  "requested_time_window"?: "morning",
  "timezone": "America/New_York",
  "notes"?: "...",
  "idempotency_key"?: "...",
  "contact"?: { "name"?, "email"?, "phone"?, "preferred_contact_method"?, "marketing_consent"? },
  "service_id"?: "<uuid, from GET .../config's services[]>",
  "location_id"?: "<uuid, from GET .../config's locations[]>"
}
```
`contact` is optional inline capture — if omitted, the request is linked to
whatever contact (if any) was already captured earlier in this same
conversation. `service_id`/`location_id` are optional (a visitor may pick
"Not sure" for either or both) and always re-validated server-side against
the resolved tenant regardless of what the config response listed —
`422` for an unknown id, an id belonging to a different tenant, or an
**inactive** service/location (inactive is treated as "not found," not
surfaced as a distinct error, matching the "never expose inactive records"
rule). If the selected service is itself restricted to one location
(`Service.location_id` set), a conflicting `location_id` is rejected
(`422`) and an omitted one is auto-filled from the service's own location.

**Date validation is timezone-aware, not UTC-as-a-proxy-for-local**: the
"today" boundary is computed from the *selected location's* IANA timezone
when one is chosen, falling back to the submitted `timezone` field
otherwise — never the server's or a browser's local clock. The submitted
value is normalized against a small known-legacy-alias map (see
"Timezones" above) and then validated as a real IANA name; `422` for a date
before the governing timezone's "today," for a `timezone` string that's
still unrecognized after normalization, or for a date more than 365 days
out.

Response always includes `status: "pending"` and a `message`
field containing the exact "pending confirmation" visitor-facing wording —
see `docs/security.md`. `reference` is the request's own UUID (non-sequential,
safe to show), not an internal sequential ID.

**`POST .../handoff-requests`** — body: `{ "reason": "...", "urgency"?: "...", "idempotency_key"?: "...", "contact"?: {...} }`.
Same inline-contact behavior as appointment requests. Repeated submissions
from the same conversation while a handoff is still `open` return the same
`reference` rather than creating duplicates. Response `message` explicitly
states this does not connect the visitor immediately — see
`docs/security.md`. Never bypasses or is reachable in place of the safety
engine's clinic-emergency response (verified live).

### Public widget error shape and safety

Same `{ "error": { "message": "...", "status_code": ... } }` shape as every
other route. Public widget errors never include a raw provider error,
stack trace, or any detail that would reveal whether an unrelated
conversation/contact exists. `429 Too Many Requests` includes a
`Retry-After` header (seconds until the limiting window resets) — see
`docs/security.md` for a bug that once silently dropped this header on
every route, not just this one.

## Client operations dashboard (dashboard, authenticated) (Phase 6)

All routes below are Bearer-token authenticated (no CSRF header needed —
same pattern as every other tenant-scoped route in this API) and tenant-
scoped via `{tenant_id}` in the path. Minimum role for every `GET` is any
active member unless noted; see docs/security.md's permission matrix for
the complete, authoritative table.

**Analytics** — `GET .../analytics/overview`, `GET .../analytics/timeseries`.
Query params: `preset` (`today`|`7d`|`30d`|`custom`, default `30d`),
`custom_start`/`custom_end` (ISO dates, required together when
`preset=custom`), `receptionist_id` (optional filter), `include_test_preview`
(bool, default `false`). `422` for an invalid preset, a missing custom
bound, an end before a start, a range exceeding
`Settings.analytics_max_range_days` (366), or an unrecognized tenant
timezone. See `app/services/analytics_service.py`'s module docstring for
the exact numerator/denominator of every field in the response, and
docs/architecture.md's "Client operations dashboard" section for the
source-classification and estimate-labeling design.

**Conversations** — `GET .../conversations` (filters: `receptionist_id`,
repeatable `source` in `{test, preview, widget}`, repeatable `status`,
`date_from`/`date_to`, `only_safety_events`, `qualification_complete`,
`search` — matches a linked contact's name/email/phone or the
`visitor_reference`; sort: `sort` in `{started_at, last_message_at}`,
`sort_direction`; bounded `limit`/`offset`, max page size 100), `GET
.../conversations/{id}` (full transcript with citations/tool-activity/
qualification/safety flags/linked contact/enquiry/appointment/handoff
records — never the system prompt, provider secrets, or a capability
token/hash).

**Contacts** — `GET .../contacts` (filters: `search`, `date_from`/
`date_to`), `GET .../contacts/{id}` (full detail plus linked
conversation/enquiry/appointment/handoff ids). List and detail expose full
PII (name/email/phone) to any active member — see docs/security.md for why
this is a deliberate policy, not an oversight.

**Enquiries** — `GET .../enquiries` (filters: `receptionist_id`, repeatable
`status`, `date_from`/`date_to`, `search`), `GET .../enquiries/{id}`,
`PATCH .../enquiries/{id}/status` — body `{"status": "...",
"expected_version": <int>}`. `422` for an invalid transition (see
docs/security.md's status-transition rules), `409` if `expected_version`
no longer matches the row's current `version` (someone else wrote first —
reload and retry, never a silent overwrite).

**Appointments** — `GET .../appointments` (filters: `receptionist_id`,
repeatable `status`, `date_from`/`date_to` against the *requested*
appointment date, `search`), `GET .../appointments/{id}`, `PATCH
.../appointments/{id}/status` (owner/admin only) — same body shape as
enquiries. Confirming, declining, or cancelling **never sends any message
to the visitor** — there is no delivery mechanism in this codebase at all.

**Handoffs** — `GET .../handoffs` (filters: `receptionist_id`, repeatable
`status`, `urgency`, `date_from`/`date_to`, `search`), `GET
.../handoffs/{id}` (includes `is_clinic_emergency`, computed from the
linked conversation's `had_clinic_emergency` flag — a clinic-emergency
handoff is never presented as an ordinary one), `POST
.../handoffs/{id}/claim` (any active member; atomic — see
docs/architecture.md — `409` if it's no longer open), `PATCH
.../handoffs/{id}/status` (`resolved`: any active member; `cancelled`:
admin/owner only; `claimed` is rejected here with a `422` pointing at the
claim endpoint instead).

**Internal notes** — `GET .../notes?entity_type=...&entity_id=...`, `POST
.../notes` (body: `entity_type` in `{conversation, contact, enquiry,
appointment_request, human_handoff}`, `entity_id`, `body`; `404` if the
entity doesn't exist for this tenant — including one that exists for a
*different* tenant, indistinguishable from "doesn't exist"), `PATCH
.../notes/{id}` (author only, `403` otherwise), `DELETE .../notes/{id}`
(author or admin/owner, `403` otherwise). Never returned to, or read by,
any public-widget route or the AI orchestrator.

**Activity** — `GET .../activity` (filters: `entity_type`, `entity_id`;
bounded `limit`/`offset`) — read-only; there is no write route, since
every event is written internally by the service that performed the
action.

**Exports** — `GET .../exports/{entity}` where `entity` is one of
`conversations` (metadata only — no message content), `contacts`,
`enquiries`, `appointments`, `handoffs`. Owner/admin only. Required
`date_from`/`date_to` query params, capped at 366 days; optional
repeatable `status` (enquiries/handoffs/appointments) and `source`
(conversations) filters, validated against the same enums the list
endpoints use — an unrecognized value is rejected with 422
(`InvalidExportFilterError`). For `appointments`, `date_from`/`date_to`
filter on `requested_date` (the appointment's own date), matching exactly
what the appointments list page shows; every other entity filters on
`created_at`. Returns `text/csv; charset=utf-8` with a
`Content-Disposition: attachment` header. All five entities are wired to
an "Export CSV" button in the dashboard UI (owner/admin only; members do
not see the control). See docs/security.md's "Export security" section
for the CSV-injection protection and row-count bound.

## Error shape

Every error response (from `app/core/errors.py`) has the same shape:
```json
{ "error": { "message": "...", "status_code": 404 } }
```
(422 validation errors additionally include `"details": [...]` — the
Pydantic error list, safely JSON-encoded via `jsonable_encoder`.)

## Not implemented in Phase 5/6

Billing/subscriptions, actual telephone calls, Twilio, WhatsApp/SMS, live
calendar booking (appointment requests are always `pending` until a human
explicitly confirms them — structured service/location *selection* is
implemented, but selecting one is never a real availability check), sending
real email, CRM synchronization, Revenue Brain / AI Sales Employee
integration, paid AI provider usage by default, an automated data-
retention/deletion job (defaults are declared and configurable; nothing
executes them yet — see `docs/security.md`), and any public marketing site
or Phase 7 industry-demo landing pages — all later, explicitly-approved
phases. A real (non-mock) provider's HTTP calls, embeddings, website
crawling, document parsing, and server-side voice processing are likewise
still out of scope; browser-native voice (Web Speech API) is implemented in
the widget bundle only, with no server-side counterpart.

Phase 6 specifically does not include: a tenant-switcher UI (a user
belonging to more than one tenant can only reach the first one in their
membership list — see docs/database-schema.md's Known limitations), an
"invite a teammate" endpoint (adding a second/third member requires a
direct database insert today), and any background job that
pre-aggregates analytics (every number is computed live, on request —
see "Analytics performance" note in docs/architecture.md for the
measured query counts/timings and when pre-aggregation would need to be
added). The dashboard shell now covers every authenticated route, and
all five export endpoints are wired to buttons in the dashboard UI (both
resolved in the Phase 6 follow-up round — see docs/PROGRESS.md).
