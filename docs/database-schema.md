# Database Schema (Phase 5)

PostgreSQL, SQLAlchemy 2.x typed models (`Mapped`/`mapped_column`), UUID
primary keys (`uuid4`, generated application-side), UTC-aware timestamps
(`TIMESTAMPTZ`, set by the database via `server_default=func.now()`, not the
application clock). Four reviewed Alembic migrations:
`backend/alembic/versions/6c6136895656_create_users_tenants_tenant_members_.py` (Phase 2),
`backend/alembic/versions/0f245f269b1d_add_industry_templates_onboarding_.py` (Phase 3),
`backend/alembic/versions/038ab1fd9129_add_conversations_conversation_messages_.py` (Phase 4), and
`backend/alembic/versions/1aa533d3cabf_add_widget_installations_visitor_.py` (Phase 5).

## Tables

### `users` (global — not tenant-owned)
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| normalized_email | VARCHAR(320) | UNIQUE, NOT NULL |
| password_hash | VARCHAR(255) | NOT NULL (Argon2id — never plaintext) |
| display_name | VARCHAR(200) | NOT NULL |
| is_active | BOOLEAN | NOT NULL, default true |
| last_login_at | TIMESTAMPTZ | nullable |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL, server-default `now()` |

### `tenants`
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| name | VARCHAR(200) | NOT NULL |
| slug | VARCHAR(220) | UNIQUE, NOT NULL (slugified name + random suffix) |
| timezone | VARCHAR(64) | NOT NULL, default `UTC` |
| status | `tenant_status` enum (`active`, `suspended`) | NOT NULL, default `active` |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

### `tenant_members`
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| tenant_id | UUID | FK → `tenants.id` `ON DELETE CASCADE`, indexed |
| user_id | UUID | FK → `users.id` `ON DELETE CASCADE`, indexed |
| role | `tenant_member_role` enum (`owner`, `admin`, `member`) | NOT NULL |
| status | `tenant_member_status` enum (`active`, `invited`, `suspended`) | NOT NULL, default `active` |
| invited_at | TIMESTAMPTZ | nullable (unused until invitation delivery ships in a later phase) |
| accepted_at | TIMESTAMPTZ | nullable, set at creation for direct-join flows |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

Unique constraint: `(tenant_id, user_id)` — one membership row per
user per tenant, enforced at the database level (not just application
logic), so a race between two concurrent "join this tenant" requests can't
create duplicates.

**Every tenant must have at least one owner** is enforced procedurally, not
by a DB constraint: `create_tenant_with_owner` always creates the tenant and
its first `owner` membership in the same transaction (with a `SAVEPOINT` to
retry cleanly on the vanishingly-rare slug collision) — there is currently
no code path that creates a `Tenant` without also creating its owner.

### `refresh_tokens`
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK → `users.id` `ON DELETE CASCADE`, indexed |
| token_hash | VARCHAR(64) | UNIQUE, NOT NULL (SHA-256 hex digest — raw token never stored) |
| family_id | UUID | NOT NULL, indexed (groups a login session's rotation chain) |
| expires_at | TIMESTAMPTZ | NOT NULL |
| revoked_at | TIMESTAMPTZ | nullable |
| replaced_by_token_id | UUID | FK → `refresh_tokens.id` `ON DELETE SET NULL`, nullable (self-referential) |
| created_at | TIMESTAMPTZ | NOT NULL |
| last_used_at | TIMESTAMPTZ | nullable |

No `updated_at` — rows are immutable once rotated/revoked except for the
two fields above, set exactly once each.

### `industry_templates` (global — not tenant-owned)
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| key | VARCHAR(64) | NOT NULL, indexed (e.g. `real_estate`, `clinic`) |
| version | INTEGER | NOT NULL |
| name, description, icon | VARCHAR | NOT NULL |
| default_terminology | JSONB | NOT NULL |
| default_welcome_message | VARCHAR(1000) | NOT NULL |
| default_suggested_questions | JSONB (list) | NOT NULL |
| default_qualification_schema | JSONB | NOT NULL |
| default_actions | JSONB (list) | NOT NULL |
| default_safety_rules | JSONB (list) | NOT NULL |
| default_workflow | JSONB (list) | NOT NULL |
| is_active | BOOLEAN | NOT NULL, default true |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

Unique constraint: `(key, version)`. **Versioned, not mutated**: changing a
template's content means adding a new `version` row for the same `key` —
existing rows are never updated in place, so a tenant that already selected
version 1 is unaffected by a later version 2. See "Seed strategy" below.

### `business_profiles` (tenant-owned, 1:1 with `tenants`)
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| tenant_id | UUID | FK → `tenants.id` `ON DELETE CASCADE`, **UNIQUE** (1:1) |
| business_name, short_description, website_url, public_email, public_phone | VARCHAR | nullable |
| industry_template_id | UUID | FK → `industry_templates.id` `ON DELETE SET NULL`, nullable |
| timezone | VARCHAR(64) | NOT NULL, default `UTC` |
| default_language | VARCHAR(8) | NOT NULL, default `en` |
| supported_languages | JSONB (list) | NOT NULL |
| onboarding_status | `onboarding_status` enum (`not_started`, `in_progress`, `completed`) | NOT NULL |
| onboarding_completed_at | TIMESTAMPTZ | nullable |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

Deliberately separate from `Tenant` (the auth/workspace identity) so public
business-facing details never mix with login/account concerns.

### `receptionists` (tenant-owned)
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| tenant_id | UUID | FK → `tenants.id` `ON DELETE CASCADE`, indexed |
| industry_template_id | UUID | FK → `industry_templates.id` `ON DELETE SET NULL`, nullable |
| template_version | INTEGER | nullable (snapshot of the version selected at the time) |
| name, welcome_message, tone, default_language | VARCHAR | — |
| supported_languages, suggested_questions | JSONB (list) | NOT NULL |
| logo_url, accent_color | VARCHAR | nullable, validated (URL / `#RRGGBB`) |
| status | `receptionist_status` enum (`draft`, `active`, `paused`) | NOT NULL, default `draft` |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

Schema supports multiple receptionists per tenant; onboarding creates one.
No AI execution happens against this table in Phase 3 — identity/config only.

### `receptionist_workflows` (tenant-owned, 1:1 with `receptionists` for the MVP)
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| tenant_id | UUID | FK → `tenants.id` `ON DELETE CASCADE`, indexed |
| receptionist_id | UUID | FK → `receptionists.id` `ON DELETE CASCADE`, **UNIQUE** |
| qualification_schema, qualification_rules | JSONB | NOT NULL — validated via `app/schemas/qualification.py` before storage |
| enabled_actions | JSONB (list) | NOT NULL — every value validated against `ALLOWED_ACTIONS` |
| safety_rules | JSONB (list) | NOT NULL — clinic/law-firm templates enforce mandatory entries (see `docs/security.md`) |
| workflow_stages | JSONB (list) | NOT NULL |
| version | INTEGER | NOT NULL, default 1, incremented on every update |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

Created automatically alongside every `Receptionist` — `GET .../workflow`
never 404s for a receptionist that exists.

### `business_locations` (tenant-owned)
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| tenant_id | UUID | FK → `tenants.id` `ON DELETE CASCADE`, indexed |
| name, address_line, city, region, country, postal_code, public_phone | VARCHAR | nullable except `name` |
| timezone | VARCHAR(64) | NOT NULL, default `UTC` |
| working_hours | JSONB | NOT NULL — validated via `app/schemas/qualification.WorkingHours` |
| is_primary, is_active | BOOLEAN | NOT NULL |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

**Partial unique index** `uq_business_locations_one_primary_per_tenant` on
`(tenant_id) WHERE is_primary = true` — a DB-level backstop making "at most
one primary location per tenant" unbreakable even under a race between two
concurrent requests, on top of the service-layer swap logic
(`app/services/location_service.py`) that unsets the old primary in its own
flush before setting the new one.

### `services` (tenant-owned)
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| tenant_id | UUID | FK → `tenants.id` `ON DELETE CASCADE`, indexed |
| location_id | UUID | FK → `business_locations.id` `ON DELETE SET NULL`, nullable — **validated at the API layer to belong to the same tenant** (a raw FK alone doesn't know about tenant boundaries) |
| name, description, category, price_note, currency | VARCHAR | nullable except `name` |
| duration_minutes | INTEGER | nullable |
| is_active | BOOLEAN | NOT NULL |
| display_order | INTEGER | NOT NULL |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

Descriptive only — no payments, no availability engine, per the zero-cost
and scope requirements for this phase.

### `faqs` (tenant-owned)
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| tenant_id | UUID | FK → `tenants.id` `ON DELETE CASCADE`, indexed |
| question | VARCHAR(500) | NOT NULL |
| answer | VARCHAR(5000) | NOT NULL |
| category, source_label | VARCHAR | nullable |
| is_active | BOOLEAN | NOT NULL |
| display_order | INTEGER | NOT NULL |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

Duplicate detection is a warning, not a block: `FAQRepository.find_similar_question`
does a normalized (trimmed/lowercased/whitespace-collapsed) exact match and
the create endpoint returns `possible_duplicate_of` alongside the new row.

### `knowledge_sources` / `knowledge_documents` / `knowledge_chunks` (tenant-owned)
| Table | Key columns |
|---|---|
| `knowledge_sources` | `type` (`knowledge_source_type` enum: `manual`, `website`, `file_upload` — only `manual` is implemented, the other two are rejected at the service layer with a clear "not yet supported" error), `title`, `status` (`content_status` enum: `active`/`inactive`) |
| `knowledge_documents` | `source_id` FK → `knowledge_sources.id` `ON DELETE CASCADE`, `title`, `raw_text` (unbounded `TEXT`, capped at 200,000 characters by schema validation), `status` |
| `knowledge_chunks` | `document_id` FK → `knowledge_documents.id` `ON DELETE CASCADE`, `content`, `chunk_index`, `created_at` only (no `updated_at` — chunks are deleted and regenerated wholesale, never edited in place) |

Chunking is deterministic (`app/services/knowledge_service.chunk_text`):
fixed 1000-character windows with 100-character overlap, computed locally
from plain string slicing — no embeddings, no external service. Search
(`POST .../knowledge/search`) uses PostgreSQL's built-in full-text search
(`to_tsvector`/`plainto_tsquery`/`ts_rank`), always filtered by `tenant_id`
first — zero-cost, deterministic, and already part of the stack.

## Enum lifecycle (Postgres-specific gotcha, handled explicitly)

SQLAlchemy's `Enum` type stores the Python enum member's **name** in
Postgres by default, not its `.value` — every enum column here explicitly
passes `values_callable=lambda cls: [m.value for m in cls]` so the database
stores `active`/`owner`/etc. (matching the API's JSON representation)
instead of `ACTIVE`/`OWNER`. This applies to all seven enums in the schema:
`tenant_status`, `tenant_member_role`, `tenant_member_status` (Phase 2), and
`onboarding_status`, `receptionist_status`, `content_status`,
`knowledge_source_type` (Phase 3).

Dropping a table does **not** drop the native Postgres `ENUM` type it used.
Both migrations' `downgrade()` explicitly drop their enum types after
dropping the tables that reference them — without this, a downgrade
followed by another upgrade would fail with `type "..." already exists`.
This was verified directly for both migrations: `alembic upgrade head` →
`alembic downgrade -1` → `alembic upgrade head` again, against the real
`ai_receptionist_dev` database, with no errors.

## Seed strategy (industry templates)

`backend/app/seed_data/industry_templates.py` defines all 10 templates as
Python `TemplateDefinition` dataclasses (versioned, `version=1` initially).
`backend/app/seed_data/seed_runner.seed_industry_templates(db)`:

1. Validates every definition's qualification schema and action list through
   the same Pydantic/allow-list validation the API uses (`_validate_definition`).
2. For each definition, checks whether `(key, version)` already exists.
3. Inserts only if missing — an existing `(key, version)` row is **never**
   updated. To change a template's content, add a new `TemplateDefinition`
   with a bumped `version`; re-running the seed inserts it as a new row and
   leaves every earlier version (and any tenant referencing it) untouched.

Run via `backend/scripts/seed_industry_templates.py` — idempotent, safe to
run repeatedly, reports created vs. skipped counts.

A separate, explicitly-invoked, development-only seed
(`backend/scripts/seed_demo_data.py`) creates three fictional demo tenants
(a real estate agency, a dental clinic, a boutique hotel) with a location,
services, an FAQ, and a knowledge document each, fully onboarded. It refuses
to run unless `ENVIRONMENT=development`, is idempotent (skips any demo
tenant whose fixed email already exists), and prints each demo user's
freshly generated one-time password to the console only — never stored in
any file or tracked document.

## Migration commands

```bash
cd backend
.venv/bin/python -m alembic current              # show applied revision
.venv/bin/python -m alembic upgrade head          # apply pending migrations
.venv/bin/python -m alembic downgrade -1          # revert one migration
.venv/bin/python -m alembic revision --autogenerate -m "description"
```

Every autogenerated migration must be hand-reviewed before being applied —
see the enum-value and enum-type-drop fixes above, both of which
autogenerate does not produce correctly on its own. No migration runs
automatically as part of application startup, tests, or any script in this
repo.

## Timezone validation

Every `timezone` column (`tenants`, `business_profiles`, `business_locations`)
is validated against a single shared source of truth:
`app.core.timezones.VALID_TIMEZONES`, a `frozenset` built once from Python's
`zoneinfo.available_timezones()`. Four schemas (`RegisterRequest`,
`TenantCreate`/`TenantUpdate`, `BusinessProfileUpdate`,
`BusinessLocationCreate`/`Update`) previously each computed their own
`zoneinfo.available_timezones()` independently — consolidated so there is
exactly one place this set is derived. `GET /api/v1/timezones` (public,
unauthenticated — needed by the registration form before any session
exists) exposes this same set, sorted, so the frontend's dropdowns are
generated from the backend's own valid set rather than the browser's
`Intl.supportedValuesOf('timeZone')` list, which includes IANA "backward"
compatibility links (e.g. `Asia/Calcutta`, `Europe/Kiev`) that Python's
tzdata build on this system does not recognize as canonical. See
`docs/PROGRESS.md`'s gap-remediation section for the full root-cause
writeup.

## Phase 4 tables

### `conversations`
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| tenant_id | UUID | NOT NULL, indexed |
| receptionist_id | UUID | NOT NULL |
| | | Composite FK `(tenant_id, receptionist_id)` → `receptionists(tenant_id, id)` `ON DELETE CASCADE` — a conversation's receptionist is guaranteed to belong to the same tenant at the database level, not just by application-level filtering. Requires `receptionists` to carry a `UNIQUE(tenant_id, id)` constraint, added by this migration. |
| mode | `conversation_mode` enum (`test`, `future_live`) | NOT NULL, default `test` — Phase 4 only ever creates `test` |
| channel | `conversation_channel` enum (`dashboard_test`) | NOT NULL — the only channel Phase 4 implements |
| provider | VARCHAR | NOT NULL — provider name active at conversation start (`"mock"` in Phase 4) |
| status | `conversation_status` enum (`active`, `completed`, `abandoned`, `failed`) | NOT NULL, default `active` |
| visitor_reference | VARCHAR | nullable — opaque, no PII assumed |
| locale | VARCHAR | NOT NULL, default `en` |
| collected_data | JSONB | NOT NULL, default `{}` — see "Why JSONB, not a field-value table" below |
| missing_required_fields | JSONB | NOT NULL, default `[]` |
| qualification_complete | BOOLEAN | NOT NULL, default false |
| safety_state | JSONB | NOT NULL, default `{}` — bounded (last 20) triggered safety category history |
| last_error_code | VARCHAR | nullable — bounded, safe-for-frontend code, never a raw exception |
| started_at, last_message_at, completed_at | TIMESTAMPTZ | `started_at` NOT NULL; the others nullable |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

### `conversation_messages`
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| tenant_id | UUID | NOT NULL, indexed |
| conversation_id | UUID | FK → `conversations.id` `ON DELETE CASCADE`, indexed |
| role | `conversation_message_role` enum (`user`, `assistant`, `system`, `tool`) | NOT NULL |
| content | TEXT | NOT NULL — the visible message text; never the full system instruction (see docs/security.md) |
| sequence_number | INTEGER | NOT NULL |
| | | `UNIQUE(conversation_id, sequence_number)` — a per-conversation total order enforced by the database, not just application logic |
| provider_message_id | VARCHAR | nullable |
| tool_name, tool_call_id | VARCHAR | nullable — populated only on `role="tool"` rows |
| tool_input, tool_output | JSONB | nullable — bounded size; tool_output never includes raw credentials |
| citations | JSONB | NOT NULL, default `[]` |
| safety_labels | JSONB | NOT NULL, default `[]` |
| latency_ms | INTEGER | nullable |
| token_usage | JSONB | nullable |
| idempotency_key | VARCHAR | nullable, partial unique index (non-null values only) per conversation — enables detecting/replaying a duplicate submission without a second DB round-trip just to check |
| created_at | TIMESTAMPTZ | NOT NULL — no `updated_at`: messages are immutable once written |

No `tenant_id` FK to `conversations.tenant_id` is declared separately here
because it's redundant with the `conversation_id` FK plus the composite FK
on `conversations` itself; the column exists purely so
`TenantScopedRepository` can filter directly without a join.

### `conversation_summaries`
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| tenant_id | UUID | NOT NULL, indexed |
| conversation_id | UUID | FK → `conversations.id` `ON DELETE CASCADE`, `UNIQUE` (one summary per conversation) |
| summary | TEXT | NOT NULL |
| captured_requirements | JSONB | NOT NULL, default `{}` |
| unresolved_questions | JSONB | NOT NULL, default `[]` |
| recommended_next_action | VARCHAR | nullable — one of the tenant's configured `enabled_actions`, never executed |
| generated_by_provider | VARCHAR | NOT NULL |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

### Why `collected_data` is JSONB, not a separate field-value table

Considered and rejected: a normalized `conversation_field_values(conversation_id,
field_key, value, ...)` table. `collected_data` stays JSONB because:

- The qualification **schema itself** is already JSONB on `receptionist_workflows`
  (Phase 3) — field keys, types, and options are dynamic, tenant-defined data,
  not a fixed set of columns. A field-value table would need its own
  type-punning (a `value` column that's sometimes a string, number, boolean,
  or list) to mirror that same dynamism, buying no real structure over JSONB.
- **Auditability doesn't require it.** Every capture/correction/rejection is
  already durably recorded as a `tool`-role `ConversationMessage` row
  (`tool_name="qualification_extraction"`, with `tool_input`/`tool_output`
  holding exactly what was captured, corrected, and rejected and why) —
  that's the audit trail, and it exists independent of how the *current*
  snapshot is stored.
- `collected_data` itself only ever needs to answer "what's the current
  value of each field" — a single JSONB read, no join, matching how it's
  actually consumed (building the qualification panel, the summary, the
  `missing_required_fields` diff).

A field-value table would add real schema and query complexity for a
requirement (auditability) already satisfied elsewhere. Revisit only if a
later phase needs to query/aggregate *across* conversations by individual
field value at the database level — Phase 4 doesn't.

### Composite FK ordering (migration note)

`conversations` has a composite FK to `receptionists(tenant_id, id)`, which
requires that pair to be unique *before* `conversations` is created. The
autogenerated migration ordered these wrong (it emitted `conversations`
before `receptionists`' new `UNIQUE(tenant_id, id)` constraint); hand-fixed
to create the constraint first in `upgrade()`, and reversed the order in
`downgrade()`. `alembic upgrade → downgrade → upgrade → check` all pass
cleanly against the approved dev database with this fix.

## Phase 5 tables

One migration (`1aa533d3cabf`) adds six new tenant-owned tables plus two
additive enum values on Phase 4's existing `conversation_mode`/
`conversation_channel` Postgres enums (`widget` on each — `future_live`
remains reserved, unused). All six new tables follow the same conventions
as Phase 1-4: `UUIDPrimaryKeyMixin`, `TimestampMixin` (except
`widget_visitor_sessions`, which follows `refresh_tokens`' manual-timestamp
convention instead — see below), explicit `tenant_id` FKs, and — where a
table also has a `receptionist_id` — a composite
`FOREIGN KEY (tenant_id, receptionist_id) REFERENCES receptionists(tenant_id, id)`
(reusing the `uq_receptionists_tenant_id_id` constraint Phase 4 added),
guaranteeing at the database level that a row can never reference a
receptionist belonging to a different tenant.

### `widget_installations`
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| tenant_id | UUID | indexed; part of composite FK below |
| receptionist_id | UUID | part of composite FK to `receptionists(tenant_id, id)` `ON DELETE CASCADE` |
| public_id | VARCHAR(64) | UNIQUE, NOT NULL (`secrets.token_urlsafe(24)` — public, non-secret; see `docs/security.md`) |
| status | `widget_installation_status` enum (`draft`, `active`, `paused`, `revoked`) | NOT NULL, default `draft` |
| allowed_domains | JSONB | NOT NULL, default `[]` (normalized bare hostnames only) |
| theme | JSONB | NOT NULL, default `{}` |
| launcher_position | VARCHAR(20) | NOT NULL, default `bottom-right` |
| privacy_notice | VARCHAR(4000) | NOT NULL, default `""` |
| ai_disclosure | VARCHAR(1000) | NOT NULL, default (a standard mock-mode disclosure sentence) |
| revoked_at | TIMESTAMPTZ | nullable |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

### `widget_visitor_sessions`
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| tenant_id | UUID | FK → `tenants.id` `ON DELETE CASCADE`, indexed |
| widget_installation_id | UUID | FK → `widget_installations.id` `ON DELETE CASCADE`, indexed |
| conversation_id | UUID | FK → `conversations.id` `ON DELETE CASCADE`, **UNIQUE** |
| token_hash | VARCHAR(64) | UNIQUE, NOT NULL (SHA-256 hex — raw capability token never stored, same pattern as `refresh_tokens.token_hash`) |
| expires_at | TIMESTAMPTZ | NOT NULL |
| revoked_at | TIMESTAMPTZ | nullable |
| created_at | TIMESTAMPTZ | NOT NULL |
| last_seen_at | TIMESTAMPTZ | nullable |

`conversation_id` is `UNIQUE`, not just indexed: a session is always scoped
1:1 to exactly one conversation, by construction, not just by convention —
see `docs/security.md`'s capability-token lifecycle. No `updated_at`,
matching `refresh_tokens`' immutable-except-two-fields convention.

### `contacts`
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| tenant_id | UUID | FK → `tenants.id` `ON DELETE CASCADE`, indexed |
| conversation_id | UUID | FK → `conversations.id` `ON DELETE SET NULL`, nullable |
| name | VARCHAR(200) | nullable |
| normalized_email | VARCHAR(320) | nullable, indexed |
| normalized_phone | VARCHAR(32) | nullable, indexed |
| preferred_contact_method | `preferred_contact_method` enum (`email`, `phone`, `either`) | nullable |
| marketing_consent | BOOLEAN | NOT NULL, default `false` |
| consent_captured_at | TIMESTAMPTZ | nullable — set only when `marketing_consent` is explicitly `true` |
| source | VARCHAR(50) | NOT NULL, default `widget` |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

`conversation_id` is `SET NULL` on delete, not `CASCADE`: a contact must
outlive the single conversation that first captured it, since it may be
found and reused across a visitor's later conversations (tenant-scoped
dedup by normalized email, then phone).

### `enquiries`
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| tenant_id, receptionist_id | UUID | composite FK to `receptionists(tenant_id, id)` `ON DELETE CASCADE`, `tenant_id` indexed |
| contact_id | UUID | FK → `contacts.id` `ON DELETE SET NULL`, nullable |
| conversation_id | UUID | FK → `conversations.id` `ON DELETE CASCADE`, **UNIQUE** |
| source | VARCHAR(50) | NOT NULL, default `widget` |
| status | `enquiry_status` enum (`new`, `qualified`, `closed`) | NOT NULL, default `new` |
| qualification_data | JSONB | NOT NULL, default `{}` |
| qualification_complete | BOOLEAN | NOT NULL |
| recommended_next_action | VARCHAR(50) | nullable |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

One row per widget conversation (enforced by the `UNIQUE` on
`conversation_id`, upserted after every message turn) — a durable,
tenant-reviewable snapshot of qualification progress, deliberately separate
from `Conversation.collected_data` (Phase 4) so a tenant retains a stable
local record even if the conversation itself is later pruned. Local-only:
no Revenue Brain or external CRM sync exists.

### `appointment_requests`
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| tenant_id, receptionist_id | UUID | composite FK to `receptionists(tenant_id, id)` `ON DELETE CASCADE`, `tenant_id` indexed |
| conversation_id | UUID | FK → `conversations.id` `ON DELETE CASCADE`, indexed |
| contact_id | UUID | FK → `contacts.id` `ON DELETE SET NULL`, nullable |
| location_id | UUID | FK → `business_locations.id` `ON DELETE SET NULL`, nullable |
| service_id | UUID | FK → `services.id` `ON DELETE SET NULL`, nullable |
| requested_date | DATE | NOT NULL |
| requested_time | TIME | nullable |
| requested_time_window | VARCHAR(50) | nullable |
| timezone | VARCHAR(64) | NOT NULL |
| notes | VARCHAR(2000) | nullable |
| status | `appointment_request_status` enum (`pending`, `confirmed`, `declined`, `cancelled`) | NOT NULL, default `pending` |
| idempotency_key | VARCHAR(128) | nullable |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

`location_id`/`service_id` are plain FKs — same-tenant validity is enforced
at the service layer (`appointment_request_service.create_appointment_request`),
the same pattern Phase 3 uses for `Service.location_id`, since a raw FK
alone cannot express "must belong to the same tenant as this request." The
public widget form does not currently expose a location/service picker (no
public endpoint lists them yet) — see `docs/api.md`'s "Not implemented"
section; a visitor names one in free-text `notes` if relevant.

### `human_handoffs`
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| tenant_id, receptionist_id | UUID | composite FK to `receptionists(tenant_id, id)` `ON DELETE CASCADE`, `tenant_id` indexed |
| conversation_id | UUID | FK → `conversations.id` `ON DELETE CASCADE`, indexed |
| contact_id | UUID | FK → `contacts.id` `ON DELETE SET NULL`, nullable |
| reason | VARCHAR(1000) | NOT NULL |
| urgency | VARCHAR(20) | nullable |
| preferred_contact_method | `preferred_contact_method` enum | nullable (same Postgres enum type as `contacts.preferred_contact_method`) |
| status | `handoff_status` enum (`open`, `claimed`, `resolved`, `cancelled`) | NOT NULL, default `open` |
| resolved_at | TIMESTAMPTZ | nullable |
| idempotency_key | VARCHAR(128) | nullable |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

### Enum-cleanup migration note

Alembic's autogenerated `downgrade()` drops tables but does **not** drop the
native Postgres enum types those tables' columns implicitly created — left
alone, re-running `upgrade()` after a `downgrade()` fails with "type already
exists." Confirmed live (not assumed): running the unfixed autogenerated
migration's `downgrade -1` and querying `pg_type` afterward showed all five
new Phase 5 enum types (`widget_installation_status`,
`preferred_contact_method`, `appointment_request_status`, `enquiry_status`,
`handoff_status`) still present after their owning tables were gone.
Hand-fixed by appending an explicit `sa.Enum(name=...).drop(op.get_bind(),
checkfirst=True)` loop to `downgrade()`, dropping `preferred_contact_method`
last (once, after both `contacts` and `human_handoffs` — the two tables
that share it — are already dropped). A related concern (that reusing one
named enum type across two `create_table()` calls in the same migration
would fail on `upgrade()`) was directly tested and disproven for the
SQLAlchemy version in use — no fix was needed there, only in `downgrade()`.

A **separate** issue affects the pre-existing `conversation_mode`/
`conversation_channel` enums: Alembic's autogenerate does not detect a
native enum *value* addition on an already-existing type at all (only
whole table/column diffs), so adding `widget` as a Python enum member
required a hand-written `op.execute("ALTER TYPE conversation_mode ADD
VALUE IF NOT EXISTS 'widget'")` (and the same for `conversation_channel`)
at the top of `upgrade()` — this was not something autogenerate produced or
would ever have produced. `downgrade()` does not attempt to remove these
added values (Postgres has no `ALTER TYPE ... DROP VALUE`; doing so would
require rebuilding the type and rewriting every row of the pre-existing
`conversations` table) — a documented, deliberately accepted asymmetry.

Full upgrade → downgrade → upgrade → `alembic current` → `alembic check`
cycle verified clean against the approved dev database, with zero orphaned
enum types and zero impact on pre-existing Phase 1-4 data, both before and
after this fix.

### A real, model-level bug this migration's review caught

The first version of all six new enum columns (`WidgetInstallationStatus`,
`AppointmentRequestStatus`, `EnquiryStatus`, `HandoffStatus`,
`PreferredContactMethod`) omitted the `values_callable=lambda cls: [m.value
for m in cls]` argument every existing native-enum column in this codebase
uses (see `conversations.mode`/`channel`/`status` for the established
pattern) — without it, SQLAlchemy stores the Python enum **member name**
(`"ACTIVE"`) rather than its `.value` (`"active"`) in the database. This
was caught by a live integration test (starting a real widget conversation
against a real database), not by a unit test with mocked data, because the
mismatch is silently self-consistent unless something else expects the
lowercase value in the actual stored row. Fixed by adding
`values_callable` to all six columns and regenerating the migration
(confirmed the regenerated migration's `CREATE TYPE ... AS ENUM(...)`
statements list lowercase values before applying it).

## What's deliberately not here yet

Live calendar/booking tables, actual telephony/WhatsApp/SMS delivery
records, structured public service/location selection for appointment
requests, and any Revenue Brain / AI Sales Employee integration tables —
all later phases, per the approved plan. The `future_live` value on
`conversation_mode` remains a forward declaration only — nothing sets or
serves it yet.

## Known limitations (Phase 3)

- **Overnight working hours are not supported.** `WorkingInterval` requires
  `start < end`; a range like `22:00`–`02:00` is rejected with a clear
  validation error rather than silently mishandled. Documented, not a bug.
- Every qualification schema model (`QualificationField`,
  `QualificationFieldOption`, `WorkingHours`, etc.) now sets
  `model_config = ConfigDict(extra="forbid")`, so an unsupported/unexpected
  JSON key in a request body is rejected with `422` rather than silently
  dropped.

## Known limitations (Phase 4)

- **`autoflush=False` (a Phase 1 session setting) means any code computing
  more than one thing derived from `MAX(...)`-style queries within a single
  uncommitted transaction must not re-query — it must compute the first
  value and increment locally.** `ConversationMessageRepository.next_sequence_number`
  was affected (see docs/architecture.md's Phase 4 section for the full
  incident writeup); the orchestrator's tool/assistant-message persistence
  block was fixed to query once per transaction and increment a local
  counter for subsequent messages in the same block.
- `ConversationOrchestrator.submit_message` manages its own short,
  explicitly-committed transactions rather than the codebase's usual
  one-commit-per-request pattern, specifically because it's a
  `StreamingResponse` body — see docs/architecture.md for why, and
  docs/security.md for the concurrency limitation this leaves undocumented
  by the automated test suite (which shares one session per test and
  therefore cannot reproduce cross-connection lock contention).

## Known limitations (Phase 5)

- **`InMemoryRateLimiter` is single-process only** — see docs/security.md.
- **Domain allow-lists are exact-match, no implicit subdomain/`www.`
  expansion** — a tenant serving from both `example.com` and
  `www.example.com` must list both.
- **Retention defaults are declared configuration, not an enforced
  policy** — no automated deletion job exists yet; see docs/security.md's
  Retention section for exactly which records currently require manual
  deletion (all of them) and the documented future deletion-job boundary.
- ~~`appointment_requests.location_id`/`service_id` have no public picker
  UI or endpoint~~ — **resolved**: `GET .../config` now lists active
  services/locations and the widget's appointment form offers them as
  optional selects, re-validated server-side (same-tenant, active-only, and
  the service→location relationship where one exists) — see
  docs/architecture.md and docs/api.md.
- **`Enquiry` is upserted best-effort after each widget message turn**, not
  inside the same transaction as the message itself — a crash between the
  two would leave `Conversation.collected_data` updated but its `Enquiry`
  snapshot briefly stale, self-correcting on the conversation's next turn.
  Acceptable for a local review record; not used as a source of truth for
  anything transactional.

## Phase 6 tables

### `internal_notes` (tenant-owned)

Staff-only annotations on exactly one operational record. Five nullable,
typed foreign keys (`conversation_id`, `contact_id`, `enquiry_id`,
`appointment_request_id`, `human_handoff_id`), each `ON DELETE CASCADE` to
its parent, rather than a polymorphic `(entity_type, entity_id)` pair — a
plain FK gives real referential integrity a generic pair cannot (a note can
never dangle after its parent is deleted). A `CHECK` constraint,
`num_nonnulls(...) = 1`, enforces "exactly one target." Soft-deleted via
`deleted_at` (never hard-deleted, so a deletion is itself auditable).
**Never** read by the AI orchestrator and **never** served to the public
widget — no route anywhere exposes this table to a visitor.

### `activity_events` (tenant-owned, append-only)

The operational audit log: `actor_user_id` (nullable — reserved for future
system-generated events), `action_type` (a free string, e.g.
`"enquiry.status_changed"`), `entity_type` + `entity_id` (a plain UUID, no
FK — an audit record must survive the deletion of the thing it describes),
and `event_metadata` (JSONB; never a secret, token, password hash, or full
message/transcript body — only small, safe summary fields like an old/new
status pair). Written only by application services
(`app/services/activity_service.py::record`); no route creates, edits, or
deletes these directly, and no public-widget code path touches this table.

### Modified tables

- **`conversations`** gains `had_safety_event` and `had_clinic_emergency`
  (booleans, default `false`) — set once, never cleared, by the
  orchestrator the first time a safety directive fires. `had_clinic_emergency`
  is a strict subset (only the `"clinic_urgent"` category), kept separately
  visible so a genuine emergency is never folded into an ordinary handoff.
- **`conversation_messages`** gains `is_fallback_response` (boolean,
  default `false`) — set by the AI provider (see `GenerateResult`/
  `StreamChunk` in `app/ai/providers/base.py`) when it found nothing to
  answer a question with. Currently meaningful only for the mock provider —
  see docs/architecture.md's Phase 6 analytics section for the full caveat.
- **`widget_visitor_sessions`** gains `is_platform_preview` (boolean,
  default `false`) — set server-side at session creation from the
  request's `Origin` against `Settings.platform_preview_origins_list`,
  never from a client-supplied field. This is the authoritative signal
  Phase 6 uses to classify a conversation as `preview` vs. genuine
  `widget` traffic (see `app/core/conversation_source.py`).
- **`enquiries`**, **`appointment_requests`**, **`human_handoffs`** each
  gain `version` (integer, default `1`) for optimistic concurrency —
  every Phase 6 status-update endpoint requires the caller to supply the
  `version` it last read; a mismatch means someone else wrote first (see
  `app/services/concurrency.py`). Status *history* is the corresponding
  `activity_events` rows, not this column.
- **`human_handoffs`** additionally gains `assigned_user_id` (nullable FK
  to `users.id`, `ON DELETE SET NULL`) — a plain FK, not tenant-composite,
  since a `User` is not itself tenant-scoped; the service layer verifies
  the assignee is an active member of the tenant before assigning.

### `enquiry_status` enum lifecycle (Phase 6)

Six new values were added via `ALTER TYPE enquiry_status ADD VALUE IF NOT
EXISTS ...`: `contacted`, `appointment_requested`, `in_progress`, `won`,
`lost`, `archived` — following the exact, already-accepted precedent from
migration `1aa533d3cabf`'s `conversation_mode`/`conversation_channel`
additions. `closed` (added in Phase 5) is **not** removed or rewritten:
Postgres has no `ALTER TYPE ... DROP VALUE`, and rewriting every existing
`enquiries` row's status would be a destructive migration for values that
are otherwise harmless to leave defined. Instead, `closed` is treated as a
legacy synonym of `archived` in the transition graph
(`app/services/enquiry_service.py::ENQUIRY_STATUS_TRANSITIONS`) — reachable
and terminal in exactly the same places, so no pre-Phase-6 row becomes a
dead end. New rows are never written with `closed`; use `archived`.

## Known limitations (Phase 6)

Two gaps from Phase 6's original round — the dashboard shell not covering
every authenticated route, and only one of five export buttons being
wired into the UI — were resolved in the Phase 6 follow-up round (see
docs/PROGRESS.md). The three limitations below remain, by explicit
decision, as documented, out-of-scope gaps:

- **No tenant switcher exists in the frontend.** `useAuth()`'s
  `memberships` array can contain more than one tenant (a user can belong
  to several), but every dashboard page always operates on
  `memberships[0]` — there is no UI to pick a different one. This
  predates Phase 6 (no earlier phase needed it either, since onboarding
  always created exactly one tenant per new user) but is now more visible:
  a user who is a member of two tenants cannot reach the second one's
  dashboard at all through the UI. Out of scope for this phase; noted here
  for whichever future phase adds team invitations.
- **No "invite a teammate" endpoint exists.** Adding a second or third
  tenant member (to test or use Phase 6's member-level permissions) requires
  a direct database insert into `tenant_members` today — there is no
  public API or dashboard UI for it. Phase 6's role-based permissions
  (owner/admin/member) are fully implemented and tested against members
  added this way; only the invitation mechanism itself is missing.
- **Analytics are computed live, with no pre-aggregation.** Every
  overview/timeseries call runs its aggregate queries against the raw
  tables on every request — there is no cache, materialized view, or
  scheduled rollup. Measured to be a fixed, small query count and a
  sub-second response at up to 8,000 conversations per tenant on a single
  local machine (see docs/architecture.md's "Analytics performance"
  section for the exact numbers and methodology); this has **not** been
  validated at production scale or under concurrent load, and the
  document above also names the concrete future step (a composite
  `(tenant_id, started_at)` index, then pre-aggregation if that stops
  being enough).
