# Database Schema (Phase 4)

PostgreSQL, SQLAlchemy 2.x typed models (`Mapped`/`mapped_column`), UUID
primary keys (`uuid4`, generated application-side), UTC-aware timestamps
(`TIMESTAMPTZ`, set by the database via `server_default=func.now()`, not the
application clock). Three reviewed Alembic migrations:
`backend/alembic/versions/6c6136895656_create_users_tenants_tenant_members_.py` (Phase 2),
`backend/alembic/versions/0f245f269b1d_add_industry_templates_onboarding_.py` (Phase 3), and
`backend/alembic/versions/038ab1fd9129_add_conversations_conversation_messages_.py` (Phase 4).

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

## What's deliberately not here yet

Lead/appointment execution tables, live/public conversation channels, and
any Revenue Brain / AI Sales Employee integration tables — all later
phases, per the approved plan. Phase 4's `mode` and `channel` enums
(`future_live`, and any channel beyond `dashboard_test`) exist as forward
declarations only — nothing in Phase 4 ever sets or serves them.

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
