# Integration contracts (Phase 8)

This document is the stable contract between AI Receptionist and any
external system it talks to — Revenue Brain, the future AI Sales
Employee, or a tenant's own webhook receiver. It is written for someone
implementing a *receiver* of these events, not for someone reading the
application source. The application source is the source of truth if this
document and the code ever disagree; file an issue if you find a
discrepancy rather than trusting whichever one you read first.

Nothing in this document assumes access to this repository's source code,
and this repository never imports from or links against Revenue Brain's or
any Sales Employee product's own codebase — the contract below is the
entire coupling between the two systems.

## 1. Outbound: the event envelope

Every event this app sends is a single JSON object with this shape:

```json
{
  "schema": "ai-receptionist.integration-event/v1",
  "event_id": "5e995be6-077a-40e6-8915-33d332873602",
  "event_type": "enquiry.qualified",
  "event_version": 1,
  "occurred_at": "2026-09-03T12:55:49.469131Z",
  "tenant_reference": "89a9c532-193c-4ba5-a414-6f4a5fdba9ec",
  "source": "ai-receptionist",
  "correlation_id": "c1c1c1c1-0000-0000-0000-000000000000",
  "causation_id": null,
  "data": { "...": "event-type-specific fields, see below" },
  "metadata": {}
}
```

| Field | Meaning |
|---|---|
| `schema` | The envelope's own schema id/version. Bump only when the *envelope shape itself* changes, independent of any one event type's `data` shape. |
| `event_id` | Stable identity of this occurrence. Use it for de-duplication on your side — the same `event_id` may arrive more than once (see §3). |
| `event_type` | One of the twelve values in §2. |
| `event_version` | That event type's own schema version — versioned independently per type, so one type's payload can change without forcing every consumer to re-validate every other type. |
| `occurred_at` | UTC, ISO-8601. |
| `tenant_reference` | An opaque identifier for the tenant this event belongs to. Do not assume any structure beyond "stable and unique per tenant." |
| `correlation_id` | Usually the conversation id this event originated from — ties related events together. May be absent. |
| `causation_id` | The id of whatever directly caused this event, when known. Usually absent in Phase 8. |
| `data` | The event-type-specific payload — see §2. |
| `metadata` | Reserved for future operational tags. Empty today. |

A receiver should validate `schema` and `event_type` against a known
allow-list and reject (not silently ignore) anything unrecognized, so a
future breaking change is caught rather than silently mishandled.

## 2. The twelve outbound event types

Every payload below is a *closed* object — no field beyond what's listed
here is ever present, and this repository enforces that server-side
(`extra="forbid"` on every payload schema — see `app/integrations/envelope.py`).

Every payload embedding a contact carries a `contact` object shaped as:

```json
{
  "contact_id": "...",
  "name": "...",
  "normalized_email": "...",
  "normalized_phone": "...",
  "preferred_contact_method": "email | phone | either | null",
  "marketing_consent": false,
  "source": "widget"
}
```

**`marketing_consent` must never be treated as blanket permission to
market to this contact via any channel your own system chooses** — it
reflects only the tenant's own record of whether *this specific contact*
opted into marketing communications from *this specific tenant's
business*, captured through the widget. Treat it as informational context
you relay to a human, not as authorization for your own system to take an
autonomous marketing action.

| `event_type` | Fired when | Key `data` fields |
|---|---|---|
| `contact.captured` | A new (not previously seen) contact record is created | `contact` |
| `enquiry.created` | A widget conversation's enquiry record is first created | `enquiry_id`, `receptionist_id`, `conversation_id`, `contact`, `status`, `qualification_complete` |
| `enquiry.qualified` | An enquiry's qualification completes (false→true transition, fires once) | same as above plus `qualification_data` (the actual captured answers) and `recommended_next_action` |
| `enquiry.status_changed` | A dashboard user moves an enquiry's pipeline status | `enquiry_id`, `previous_status`, `new_status` |
| `appointment_request.created` | A visitor submits an appointment request | `appointment_request_id`, `contact`, `requested_date`, `requested_time`, `timezone`, `status` (always `pending` — see below) |
| `appointment_request.status_changed` | An owner/admin confirms/declines/cancels | `appointment_request_id`, `previous_status`, `new_status` |
| `human_handoff.requested` | A visitor requests a human follow-up | `handoff_id`, `contact`, `reason`, `urgency`, `status` |
| `human_handoff.status_changed` | Claimed / resolved / cancelled | `handoff_id`, `previous_status`, `new_status` |
| `conversation.completed` | A conversation is explicitly marked complete | `conversation_id`, `mode`, `channel`, `message_count` (never message content) |
| `conversation.abandoned` | An explicit sweep (`app/services/conversation_sweep_service.py`, run via `scripts/sweep_stale_conversations.py` — see §9) finds ACTIVE conversations idle past a threshold and transitions them | same shape as `conversation.completed` |
| `safety.escalation_detected` | The deterministic safety engine intercepted a message | `conversation_id`, `category` (e.g. `clinic_urgent`), `channel` — **never the triggering message text** |
| `connection.test_event` | An owner/admin clicks "send test event," or the integration lab | `message`, `triggered_by` |

**`appointment_request_request.status` is always `pending` at creation
time** — this product has no live calendar integration; a request is
never automatically confirmed. Never present it to an end user as booked.

**`safety.escalation_detected` never includes the message that triggered
it.** It exists so a receiving system can flag a conversation for human
review, not to hand a potentially sensitive (e.g. self-harm-related)
message to a third-party system. If you need to review the actual
conversation, do so inside the AI Receptionist dashboard itself.

## 3. Delivery guarantees

Delivery is **at-least-once, never at-most-once, and only best-effort
ordered**. Concretely:

- The same `event_id` may be delivered to you more than once (a retry
  after a timeout where your receiver actually processed the request but
  the response was lost is the common case). **Your receiver must be
  idempotent on `event_id`.**
- Two events for the same tenant may arrive out of `occurred_at` order
  under retry/backoff. If order matters to you, sort by `occurred_at`
  yourself; do not assume delivery order.
- A delivery that keeps failing is retried with exponential backoff (base
  2s, cap 15 minutes, full jitter) up to a configurable attempt ceiling
  (default 8), after which it is marked dead-lettered. An owner/admin can
  manually replay a dead-lettered delivery from the dashboard or CLI —
  dead-lettered events are never silently dropped, but they are also
  never automatically retried past the ceiling.

## 4. Request signing (both directions)

Every signed request — outbound from this app to you, and inbound from
you to this app — uses the same HMAC-SHA256 scheme.

Headers:

| Header | Meaning |
|---|---|
| `X-Integration-Signature` | `hex(HMAC-SHA256(secret, signing_string))` |
| `X-Integration-Timestamp` | Unix seconds at signing time |
| `X-Integration-Delivery-Id` | A per-attempt id (differs on retry) — outbound only |
| `X-Integration-Event-Id` | The envelope's `event_id` |
| `X-Integration-Schema-Version` | The envelope `schema` string |

Signing string: `f"{timestamp}.{delivery_id}.{event_id}.{schema_version}."`
followed by the exact raw request body bytes (concatenated, not
JSON-encoded together). Verify with a constant-time comparison
(`hmac.compare_digest` or equivalent) — never `==`.

A receiver should reject a request whose `X-Integration-Timestamp` is more
than 300 seconds from its own clock, to bound how long a captured request
could be replayed even if a valid signature were somehow obtained.

Because `delivery_id` (not just `event_id`) is part of the signed
material, a retried delivery of the same event produces a different
signature each attempt — do not use signature equality as a
de-duplication signal; use `event_id` in the body instead (see §3).

## 5. Inbound: sending events to AI Receptionist

`POST /api/v1/integrations/inbound/events`, authenticated with an
API key (`X-Integration-Api-Key` header, issued once per connection
from the AI Receptionist dashboard — see §7) plus the HMAC signature
described in §4, using that same connection's shared secret. There is no
tenant id in the URL: the tenant is resolved entirely from the API key.

Request body (closed schema — `extra="forbid"`):

```json
{
  "external_event_id": "your-own-idempotency-key",
  "event_type": "lead.status_updated",
  "event_version": 1,
  "data": {
    "external_reference": "your-own-id-for-the-lead",
    "note": "free-text note, max 2000 characters"
  }
}
```

Allowed `event_type` values today: `lead.status_updated`, `lead.note`.
Any other value is rejected with `422` before anything is persisted.

**Phase 8 scope boundary, deliberate:** an inbound event is durably
recorded (and shown in the tenant's dashboard activity log) but **never
automatically mutates a business record** — it cannot change an Enquiry's
status, confirm an appointment, or resolve a handoff. There is no
"arbitrary mutation" surface here by design. A future phase that wants an
inbound event to drive a real state transition should do so through the
existing, already-validated service-layer transition functions, not by
extending this endpoint's own reach.

Responses:

- `200 {"status": "processed", "external_event_id": "..."}` — first time
  seen.
- `200 {"status": "duplicate", "external_event_id": "..."}` — the same
  `external_event_id` was already processed with an identical body; a
  harmless replay.
- `409` — the same `external_event_id` arrived with a **different** body
  than before. This is a conflict, not a replay; use a new
  `external_event_id` for a genuinely new occurrence.
- `401` — any authentication failure (missing credentials, unknown key,
  bad signature, expired timestamp, or a key with no signing secret
  configured). Deliberately the exact same generic error for every case —
  do not attempt to distinguish "key not found" from "signature invalid"
  from the response; that ambiguity is intentional.
- `422` — the request body doesn't match the closed schema above, or
  `event_type` isn't recognized.
- `429` — rate limited (30 requests/60 seconds per API key by default).

## 6. Known limitations (stated honestly, not hidden)

- **At-least-once, not exactly-once.** See §3. There is no way for this
  app to guarantee a receiver never sees a duplicate; idempotency is the
  receiver's responsibility.
- **A narrowed, not eliminated, DNS-rebinding window in SSRF protection.**
  The destination is resolved and validated (`app/core/ssrf_guard.py`)
  immediately before every delivery attempt, and the actual TCP connection
  is then pinned to exactly that validated IP address
  (`app/integrations/pinned_transport.py`), rather than letting the HTTP
  client re-resolve DNS on its own — this closes the classic gap where
  validation and connection could resolve two different addresses. TLS
  hostname verification and the HTTP `Host` header still use the original
  hostname, so pinning never weakens TLS. **What this does not, and
  cannot, protect against:** if the authoritative DNS answer is *already*
  the attacker's chosen address at the exact moment `ssrf_guard` performs
  its own resolution, validation sees only that (already-compromised)
  answer and — correctly, from its own perspective — either accepts or
  rejects based on it; pinning guarantees the connection matches what was
  validated, but cannot detect that the validated answer was itself
  misleading. Do not claim complete DNS-rebinding protection from this
  codebase alone. **Production deployment requirement:** this
  application-level pinning is a defense-in-depth measure, not a
  substitute for network-level egress filtering — production deployments
  must additionally restrict the backend's own network egress (e.g. a
  security group / NACL / proxy policy) so it cannot reach private,
  loopback, or link-local ranges regardless of what this code decides.
- **Single-key encryption, no online rotation.** Every stored secret
  records which encryption key version it was encrypted under, but this
  codebase does not implement multi-key rotation logic (trying an older
  key version if the current one fails) — rotating
  `INTEGRATION_ENCRYPTION_KEY` today requires re-entering every stored
  signing secret.
- **Connection health counters are best-effort under concurrency.** A
  connection's `failure_count`/`last_delivery_status` fields are a
  read-modify-write, not a SQL-level atomic increment — under many
  concurrent deliveries for the *same* connection this can lose an
  increment. Acceptable because these are operator-facing health signals,
  never a delivery gate or security boundary.
- **Rate limiting is single-process.** The inbound API's rate limiter
  (`app/core/rate_limit.py`) is in-process memory, not shared across
  multiple backend worker processes — see that module's own docstring.

## 7. Connectors, in brief

Four connector types exist today, all sharing the envelope/signing
scheme above:

- **mock** — deterministic, zero-network. Used by tests and the
  integration lab; never reaches a real destination.
- **webhook** — generic signed HTTPS POST to any tenant-configured URL.
- **revenue_brain** — same delivery mechanism as `webhook`, its own
  connector type so it gets its own dashboard identity and defaults.
- **sales_employee** — same delivery mechanism, restricted to a smaller
  allow-list of event types (never `safety.escalation_detected`) and
  explicitly, permanently outbound-notification-only: nothing in this
  codebase lets a Sales Employee connection trigger an autonomous
  message/call/email to a lead. See `app/integrations/connectors/sales_employee.py`.

A connection's inbound API key is shown exactly once, at creation or
rotation — see the dashboard API's `POST /tenants/{id}/integrations/{id}/inbound-key`.
Only its hash is ever stored.

## 8. Field mapping (outbound only)

A webhook-family connection may configure a closed field-mapping
transform applied to the outbound `data` object only (never the
envelope's own fields): `rename` (old key → new key), `include` (an
allow-list — everything else is dropped), `omit` (drop named keys), and
`defaults` (fill a key only if still absent after the above). There is no
expression language, no templating, and nothing that executes code — see
`app/integrations/field_mapping.py`. The dashboard's connection detail
page includes a live preview of this transform against fictional sample
data (`POST .../preview-mapping`) so an owner/admin can check a mapping
before saving it, without sending anything real.

## 9. Managing connections: dashboard, lab, and health

Every connection is created, configured, verified, paused/resumed,
disabled, and rotated (both the outbound signing secret and the inbound
API key) from the authenticated dashboard under
`/dashboard/integrations/*` — never by editing the database directly.
Owner/admin can manage; a member has read-only access; a non-member gets
a 404, not a 403 (see docs/security.md). An inbound API key and a newly
rotated signing secret are each shown exactly once, in the browser's own
React state — never written to `localStorage`, `sessionStorage`, a URL,
or any persisted client-side store, and never returned by the API a
second time (only the key's prefix + last four characters are ever
shown again).

`/dashboard/integrations/lab` is a local, zero-network demonstration of
this whole contract — every connection it creates uses the `mock`
connector type, so nothing it does ever reaches a real destination, sends
a real message, or calls a paid AI provider. It exists so an owner/admin
(or a reviewer) can see qualified-lead production, inbound priority-event
delivery with real client-side HMAC signing, dead-letter + replay,
duplicate-inbound idempotency, a revoked API key failing authentication,
and a rotated signing secret invalidating the old signature — all against
the real backend, all fictional data, all in one click.

`GET /tenants/{id}/integrations/health` (surfaced on the integrations
list page) returns a tenant-scoped summary: connection status breakdown,
pending-event count, retry backlog, oldest-pending-event age,
dead-letter count, successful/failed delivery counts over a configurable
window (default 24h, capped at 168h), a success rate, p50/p95 delivery
latency (sampled, capped at 500 rows), last success/failure timestamps,
and structured warnings (missing encryption key configured, a connection
with repeated consecutive failures, a stale retry backlog, a disabled
connector still enabled on a connection). **A rate or latency figure is
`null`, never `0`, when there is no data to compute it from** — a
tenant with zero deliveries in the window has a `null` success rate, not
a misleading `0%`. Marking a connector "healthy" always requires
evidence of an actual successful delivery or verification for that
specific connector, never just "the main API responded" — see
`app/services/integration_health_service.py`.

`conversation.abandoned` is produced by an explicit, bounded sweep
(`app/services/conversation_sweep_service.py`) that finds ACTIVE
conversations idle past a configurable threshold (default 60 minutes) and
transitions them to `ABANDONED`, producing the event the same way
`conversation.completed` is produced on explicit completion. It is
exposed only as a CLI (`python -m scripts.sweep_stale_conversations
[--stale-after-minutes N] [--batch-limit N] [--tenant-id ID]`, or
`python scripts/sweep_stale_conversations.py ...`) — **there is no
automatically running scheduler for it in this codebase**; a production
deployment that wants this event must run the CLI on its own schedule
(cron, a scheduled task runner, etc.).
