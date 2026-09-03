# Architecture

## Overview

AI Receptionist is a single, configurable multi-tenant engine — not a set of
per-industry applications. Industry behavior (terminology, welcome message,
suggested questions, qualification fields/rules, enabled actions, safety
rules, workflow stages) is **data** — implemented as of Phase 3 — resolved
at onboarding time from a global, versioned `IndustryTemplate` and snapshot
into a tenant's own `Receptionist`/`ReceptionistWorkflow` rows. There is no
industry-specific branching anywhere in the codebase: every route, service,
and validator is industry-agnostic and operates purely on the stored
configuration.

```
frontend/  Next.js 15 (App Router, TypeScript, Tailwind) — public site,
           onboarding, client dashboard
backend/   FastAPI (Python 3.12, Pydantic v2, SQLAlchemy 2.x, Alembic)
widget/    Embeddable receptionist widget — public API surface only
docs/      Architecture, API, security, progress documentation
scripts/   Safe local-dev and verification scripts
```

## Backend structure (Phase 3)

```
backend/app/
  main.py            Application factory (create_app)
  config.py          Environment-driven Settings (pydantic-settings)
  logging_config.py  Structured (JSON) logging setup
  db/
    base.py          Shared SQLAlchemy declarative Base
    session.py       Engine/session management, commit-on-success/
                      rollback-on-exception per request, check_database_connection()
  models/            User, Tenant, TenantMember, RefreshToken (Phase 2);
                      IndustryTemplate, BusinessProfile, Receptionist,
                      ReceptionistWorkflow, BusinessLocation, Service, FAQ,
                      KnowledgeSource/Document/Chunk (Phase 3) + mixins, enums
  repositories/      Plain (User, Tenant, TenantMember, IndustryTemplate,
                      BusinessProfile) and tenant-scoped (TenantScopedRepository
                      + one subclass per tenant-owned Phase 3 model)
  services/          auth_service.py, tenant_service.py (Phase 2);
                      onboarding_service.py, receptionist_service.py,
                      location_service.py, knowledge_service.py (Phase 3) —
                      business logic, independent of FastAPI/HTTP concerns
  seed_data/         industry_templates.py (10 versioned template
                      definitions), seed_runner.py (idempotent upsert),
                      demo_tenants.py (dev-only fictional demo seed)
  api/
    deps.py          get_current_user, get_tenant_context, require_tenant_role
    cookies.py       set_auth_cookies / clear_auth_cookies
    v1/
      router.py      Aggregates all v1 routers
      health.py, auth.py, tenants.py           (Phase 1/2)
      industry_templates.py, onboarding.py,
      receptionists.py, locations.py,
      services.py, faqs.py, knowledge.py       (Phase 3)
  core/
    errors.py          Central exception handlers (consistent error shape;
                        see docs/security.md for a Phase 3-discovered fix)
    security.py         Argon2 hashing, JWT encode/decode, refresh-token generation
    csrf.py              Double-submit CSRF dependency
    normalization.py     Email normalization
    allowlists.py        Server-maintained allow-lists (actions, field types,
                          rule types, mandatory safety rules, languages)
    text_safety.py        Plain-text validation/sanitization helpers
  schemas/             Pydantic request/response models, incl.
                        qualification.py (field/rule/working-hours schemas
                        shared across the whole Phase 3 surface)
```

`app/db/base.py` and the Alembic foundation from Phase 1 are exactly what
every subsequent phase's models plug into — no earlier scaffolding needed
to change.

## Database connectivity model

`DATABASE_URL` is optional at the settings level. `check_database_connection()`
distinguishes three states, all handled without raising:

- `not_configured` — no `DATABASE_URL` set (expected in a fresh checkout)
- `ok` — connected successfully
- `unavailable` — configured but unreachable (connection refused, timeout, etc.)

The `/health` and `/api/v1/health` endpoints report `status: "ok"` when the
database is either connected or simply not configured yet, and
`status: "degraded"` only when it's configured but unreachable — so the
service never crashes or 500s because the database is temporarily down.

## Authentication (implemented — Phase 2)

Secure email/password auth: Argon2id password hashing, short-lived JWT
access tokens (in-memory on the frontend, never `localStorage`), rotating
opaque refresh tokens (`HttpOnly` cookie) with reuse detection, and tenant
membership + role enforcement (`owner`, `admin`, `member`). No magic-link or
OAuth in the MVP. The auth module is isolated behind three replaceable seams
(token issuance, user storage, session mechanics) so it can later be
swapped for shared AI Business Engine authentication without touching
tenant/permission logic. Full detail: `docs/security.md`.

## Integration secrets (deferred to Phase 8)

Per approved Decision 2, `IntegrationConnection` (introduced in a later phase)
will store only non-sensitive metadata and status in Phase 1–7. No secret
storage mechanism is implemented yet. **Future requirement to satisfy before
Phase 8 ships:** integration credentials must be encrypted at rest (e.g. via
an application-level envelope key or a secrets manager) — never plaintext in
the database, never placeholder values checked into config.

## Tenant isolation model (implemented — Phase 2, extended in Phase 3)

Every tenant-owned table carries `tenant_id` and goes through
`TenantScopedRepository` (`app/repositories/base.py`), which filters every
query by a `tenant_id` that can only come from a trusted, server-resolved
`TenantContext` — never from client input. As of Phase 3 this covers eight
tenant-owned tables (`BusinessProfile`, `Receptionist`,
`ReceptionistWorkflow`, `BusinessLocation`, `Service`, `FAQ`,
`KnowledgeSource`, `KnowledgeDocument`, `KnowledgeChunk`), each with its own
thin repository subclass. Automated cross-tenant isolation tests run at both
the HTTP layer and the repository layer directly
(`backend/tests/tenant_isolation/`) for every one of them, and are part of
the standard verification suite. See `docs/security.md` and
`docs/database-schema.md` for detail, including the one case (`Service.location_id`)
where a client-supplied cross-reference needed its own explicit
same-tenant check beyond the URL path.

## Industry template & onboarding model (implemented — Phase 3)

`IndustryTemplate` is global, versioned catalog data — tenants can only
read it (no API route exists to mutate it). Selecting a template
(`POST /tenants/{id}/select-industry`) snapshots its current
`default_qualification_schema`/`default_actions`/`default_safety_rules`/
`default_workflow` into the tenant's own `ReceptionistWorkflow` row, only
when that workflow still looks untouched — so later edits to the global
template, or re-selecting a template, never silently overwrite a tenant's
customization. Onboarding progress (`GET /tenants/{id}/onboarding`) is
computed live from the tenant's actual stored data on every call rather
than tracked via a separate "current step" pointer, so it can never drift
out of sync with reality and survives a page refresh for free. See
`docs/api.md` and `docs/database-schema.md` for the full model/endpoint
detail.

## AI conversation engine (implemented — Phase 4)

Phase 4 adds a private, authenticated test conversation engine — no public
widget, no live telephony/SMS/WhatsApp, no human handoff execution, no
billing. Everything runs against the deterministic mock provider by default
and requires zero paid credentials.

```
backend/app/ai/
  providers/
    base.py            Provider-independent contract: typed request/response
                        objects, generate()/stream()/summarize()/capabilities()
    mock.py            MockProvider — deterministic, zero-cost, default
    openai_provider.py  Disabled stub unless OPENAI_API_KEY is configured
    anthropic_provider.py Disabled stub unless ANTHROPIC_API_KEY is configured
    factory.py          get_provider(settings) — validated selection, fails
                        safe (controlled ProviderConfigurationError) on an
                        unknown provider or missing credentials
  safety.py             evaluate_safety() — deterministic, outside any model,
                        clinic/legal/general rules (see docs/security.md)
  retrieval.py           retrieve() — reuses Phase 3's tenant-scoped full-text
                        search across FAQs/knowledge/services/locations/hours
  system_instructions.py build_system_instruction() — server-owned policy +
                        validated config; untrusted knowledge is delimited
                        and never treated as authority (see docs/security.md)
  qualification.py       Deterministic extraction/validation/correction for
                        every Phase 3 field type, scoped to the one pending
                        field per turn
  tools/                 Server-defined, allow-listed read-only tools:
                        search_business_knowledge, list_services,
                        get_business_hours, get_business_profile
  orchestrator.py        ConversationOrchestrator — the state machine tying
                        every step above together (see below)
```

### Orchestration and the streaming-transaction problem

`ConversationOrchestrator.submit_message` is a generator yielding SSE event
dicts, driving: safety pre-check → persist user message → retrieval →
qualification extraction/validation → tool-call decision → tool execution →
streamed final response → persist assistant message + tool events + updated
conversation state → (on completion) generate a summary.

The route (`POST .../messages`) returns a `StreamingResponse` whose body is
this generator. This interacts badly with the rest of the codebase's normal
"one commit per request, via `Depends(get_db)`" pattern (documented in
`app/db/session.py`): that dependency's cleanup — the one place that calls
`db.commit()`/`db.close()` — fires as soon as the route function *returns
the response object*, which is *before* the generator body has run at all
(the body only executes later, as Starlette drains it). Two consequences,
both discovered via live testing rather than the unit suite (see
docs/PROGRESS.md's Phase 4 entry for why):

1. **A row lock held forever.** The orchestrator locks the conversation row
   (`SELECT ... FOR UPDATE`, via `ConversationRepository.get_for_update`) to
   serialize two submissions against the same conversation. If nothing
   inside the generator ever explicitly commits, that lock's implicit
   transaction is never released — the *next* message to the same
   conversation blocks forever. The fix: the orchestrator manages its own
   short transactions explicitly, committing at each phase boundary and
   re-acquiring the lock before the next phase, so the lock is **never**
   held across the provider streaming call in the middle of a turn.
2. **A connection leaked after every request.** Even with those explicit
   commits, SQLAlchemy's `expire_on_commit=True` default means any
   attribute read *after* the last commit (e.g. building the final
   `conversation.updated` SSE event from an already-committed `Conversation`
   object) silently reopens a fresh implicit transaction — one nothing
   would ever close, since `Depends(get_db)`'s own cleanup already ran.

The first fix attempt for (2) kept using the `db` injected via
`Depends(get_db)` and patched around the symptom: the orchestrator captured
needed values into locals before each commit, and the route wrapped the
generator in `try/finally: db.rollback()`. That reduced *how often* a
transaction was left open, but the underlying design flaw remained —
nothing ever called `db.close()` at the generator's true end, because
`Depends(get_db)`'s own close already fired before the generator ran.
Empirically, the connection was still reclaimed promptly by CPython's
reference counting once the generator object itself became unreachable —
but "reclaimed by refcounting" is not a guarantee `session_scope` (below)
is willing to make, since it is implementation-specific (CPython-only) and
not something correctness should ever depend on.

### Explicit session ownership (`app/db/session.py`)

Every session's full lifecycle — creation, commit-or-rollback, and close —
is owned by exactly one function: `session_scope()`, a plain context
manager. `get_db()` (the FastAPI dependency every non-streaming route uses)
is now just `with session_scope() as db: yield db` — a thin adapter, not a
second implementation of the same contract. Nothing else in the codebase
creates a session, and nothing else closes one it did not create — verified
by a source-level test (`tests/test_db_session_lifecycle.py`) asserting
`.close(` never appears in `app/ai/orchestrator.py` or any
`app/repositories/*.py` module.

```python
@contextmanager
def session_scope():
    db = get_session_factory()()
    try:
        yield db
        db.commit()
    except BaseException:      # not `Exception` — see below
        db.rollback()
        raise
    finally:
        db.close()             # unconditional — always runs
```

`except BaseException`, not `Exception`, is deliberate: `GeneratorExit` (a
generator being `.close()`d — see the streaming section below),
`KeyboardInterrupt`, and `SystemExit` are not `Exception` subclasses, and
every one of them still needs the transaction rolled back and the
connection returned before it propagates. The `finally` is unconditional on
top of that, so even a broken `rollback()` itself still results in
`close()` running. None of this depends on `__del__`, garbage collection,
reference counting, or a pool timeout — every exit path is an explicit call
inside this one function, proven directly (mock session, no real database)
in `tests/test_db_session_lifecycle.py`.

**The streaming route's problem was never really "how do we clean up
better" — it was "this route can't use `Depends(get_db)` for its real work
at all.**" `send_test_message` now takes a second dependency,
`session_scope_factory` (`Depends(get_session_scope_factory)` in
`app/api/deps.py`) — not a session, the *callable* that opens one — and
opens its own `with session_scope_factory() as stream_db:` block that stays
open for the streaming generator's entire lifetime, closing deterministically
when that block exits, on every path: normal completion, a handled
`ConversationError`, any other exception, or the generator being closed
early (see below). The `db` obtained via the ordinary `Depends(get_db)`
parameter on that same route is used for nothing but the one pre-stream
existence/status check, which runs synchronously before the route returns
anything — `get_db`'s normal contract already handles that correctly.

Depending on `get_session_scope_factory` rather than calling `session_scope`
directly is what lets tests substitute their own session-owning context
manager for that one route: `session_scope` is a plain module function, not
something `app.dependency_overrides` can intercept, but a factory function
depended on via `Depends()` can be. `db_backed_client` (the shared-session
test fixture) overrides it with one that applies the same
commit-or-rollback contract against the fixture's single shared session,
but deliberately never calls `.close()` on it — that session is owned by
the `db_session` fixture, which closes it exactly once in its own teardown;
closing it mid-test would detach every ORM object the test still holds. This
is a documented, test-only relaxation of *one specific override*, not a
weakening of `session_scope` itself, which is unmodified and always closes.
`tests/integration/`'s `real_client` installs no override at all, so it
exercises the real `session_scope` end to end.

### A second, deeper streaming bug: Starlette never closes a sync generator on disconnect

Fixing the connection leak above (committing/rolling back and closing
deterministically at the generator's own end) still left one gap, found
only by testing against a **real TCP client** — `TestClient`'s in-process
ASGI transport runs the whole (mock-provider-backed, near-instant) response
to completion before a client can realistically disconnect mid-stream, so
it could never have caught this either. Closing a real `httpx.Client`
stream early, mid-turn, left a connection sitting "idle in transaction"
*indefinitely* — not for a moment, for as long as the server process ran.

The cause, confirmed by reading Starlette's source
(`starlette/concurrency.py`): `StreamingResponse` given a *sync* generator
wraps it in `iterate_in_threadpool`, which dispatches each `next()` call to
a worker thread — and never calls `.close()` on that generator under any
circumstance. On a real disconnect, `StreamingResponse.__call__` cancels
the task group, which only stops the coroutine from *awaiting* the next
`next()` result; it cannot and does not interrupt the worker thread already
running, and nothing afterward ever resumes or closes the generator. The
sync generator — including its open `with session_scope_factory():` block —
is left permanently suspended mid-turn.

The fix: `send_test_message`'s sync generator (`sync_event_stream`) is now
adapted into a genuinely `async` one, `stream_sync_generator`
(`app/api/v1/conversations.py`), before being handed to `StreamingResponse`.
An async generator is used by Starlette directly, with no threadpool
wrapper — so a cancelled task delivers `CancelledError` straight into *its*
suspension point, and its own `finally: await run_in_threadpool(sync_gen.close)`
deterministically closes the wrapped sync generator (and therefore
`session_scope_factory`'s session) before the coroutine finishes unwinding.
One further, easy-to-miss subtlety: a bare `StopIteration` raised while
`next()`ing the sync generator cannot be caught as `StopIteration` once it
crosses an `await` boundary — PEP 479 converts it to `RuntimeError:
coroutine raised StopIteration` first — so the thread-side helper
(`_next_or_raise_stop_marker`) converts it to a distinct marker exception
before it ever crosses that boundary, exactly mirroring Starlette's own
`_next`/`_StopIteration` pair inside `iterate_in_threadpool`.

`stream_sync_generator` is a standalone, directly-testable function
specifically so its cancellation-safety has fast unit coverage
(`tests/test_streaming_generator_lifecycle.py`) that doesn't depend on
reproducing a real, precisely-timed network disconnect: a trivial sync
generator stands in for `sync_event_stream`'s real body, and the test calls
`.aclose()` on the async wrapper mid-stream — the same mechanism a cancelled
Starlette task ultimately delivers — and asserts the sync generator's own
`finally` ran. This test was verified to actually catch the bug it exists
for: temporarily removing the wrapper's `finally: close()` call and
re-running it reproduces the exact failure, confirmed, then reverted.

A related, separate bug surfaced through the same live-testing pass: because
this session's engine uses `autoflush=False` (a Phase 1 setting), calling
`ConversationMessageRepository.next_sequence_number()` more than once inside
one uncommitted transaction returns the *same* value each time — none of the
just-`add()`ed rows are visible to a fresh `MAX(sequence_number)` query until
a flush actually happens. Persisting a tool-call message and the assistant's
reply in the same transaction (the common case whenever a tool is invoked)
therefore raced to insert the same sequence number, caught only at flush
time by the `uq_conversation_messages_sequence` unique constraint. Fixed by
querying the next sequence number once per transaction and incrementing a
local counter for every subsequent message in that same block, rather than
re-querying.

None of the 255 backend tests running at the time caught these — the test
fixture (`db_backed_client`) deliberately reuses one `Session` across every
request in a test (for savepoint-based rollback isolation), which collapses
what would be several independently-pooled connections in production into
one, masking exactly the kind of cross-connection lock contention and
connection-lifecycle bug described above. **This gap is now closed by a
dedicated automated regression suite** — see the next section.

### PostgreSQL multi-connection integration tests

`backend/tests/integration/` (marker: `multiconn`) exists specifically to
give the three bugs above — and the general class of bug they represent —
automated, repeatable regression coverage, without falling back into the
same shared-session blind spot that let them through the first time.

```
backend/tests/integration/
  conftest.py   real_client (TestClient with NO dependency override — every
                request resolves the app's actual get_db, i.e. a genuinely
                fresh Session on a genuinely fresh pooled connection, exactly
                like production); cleanup_tenants (deletes exactly the
                tenants/users a test created, after re-verifying the database
                name, even on failure); idle_in_transaction_count() and
                held_locks_on() — observable pg_stat_activity/pg_locks
                checks, not internal-state assertions
  helpers.py    register_tenant/setup_active_receptionist/start_conversation/
                send_message — all through the real HTTP API
  test_conversation_concurrency.py
                One test class per defect/behavior: row lock across
                streaming, connection-pool leak, sequence-number collision,
                idempotent replay, concurrent submission, failure recovery,
                and a generator-close cleanup test for the SSE-disconnect case
```

Key design choices:

- **Genuinely separate connections without a live subprocess.** `real_client`
  is still `TestClient` (in-process ASGI), but with no session override —
  each HTTP call goes through the app's real `Depends(get_db)`, so FastAPI's
  own dependency-injection machinery hands out a fresh `Session`/pooled
  connection per call, exactly as a real deployed server would. This was
  verified, not assumed: a test deliberately re-broke the sequence-number
  fix (reverted immediately after) and confirmed this suite catches it —
  see docs/PROGRESS.md's Phase 4 entry.
- **Bounded timeouts via a thread pool, not `httpx` timeouts.** TestClient's
  ASGI transport has no real socket to time out on, so a genuine lock
  regression would otherwise hang the test (and the whole run) forever.
  Every request goes through a per-test `ThreadPoolExecutor`, and the test
  calls `future.result(timeout=...)` — a regression fails loudly with a
  `TimeoutError` instead. True concurrent submissions (scenario E) submit
  both requests to the executor before waiting on either result, so they
  genuinely overlap in time on two separate connections.
- **Observable behavior, not internals.** `idle_in_transaction_count()` and
  `held_locks_on()` query `pg_stat_activity`/`pg_locks` directly — the same
  signals that diagnosed the original bugs live — rather than asserting on
  SQLAlchemy session/pool internals that could pass while the actual
  database-visible behavior regressed.
- **Documented, tested concurrent-submission behavior.** Two simultaneous
  submissions to the same conversation serialize at the row lock: both
  complete successfully (in whatever order), sequence numbers stay unique
  and strictly increasing, neither is rejected with a conflict response.
  This is a deliberate design choice (simpler than distinguishing
  "acceptable serialization delay" from "reject and ask the client to
  retry"), tested deterministically via two requests submitted to the
  executor together.
- **Isolated cleanup.** Every test registers a brand-new tenant (and its
  owning user) via the real `/auth/register` endpoint with a uniquely
  suffixed email/workspace name, and hands both ids to `cleanup_tenants`,
  which re-verifies the database name and deletes exactly those rows —
  cascading to their conversations/messages/receptionists — in a fixture
  `finally`, so cleanup runs even when the test itself fails.

### SSE disconnect / generator-close: what's covered and what's still deferred

Two distinct properties, both now verified, plus one deliberately deferred
gap:

1. **The row lock is never held across a `yield`.** Every `get_for_update()`
   call in the orchestrator is immediately followed by a `commit()`/
   `rollback()` with no `yield` in between — a generator can only be
   interrupted at a `yield` point, so it can never be closed while actually
   holding the row lock. `TestGeneratorCloseCleanup`'s first test proves
   this directly against the orchestrator (`.close()` right after the first
   yield, deterministic, no timing).
2. **The session is now actually released on a real disconnect.** This was
   *not* true until the fix described above — a real disconnect used to
   leak a session/connection forever, only found by testing against a real
   TCP client. `stream_sync_generator` fixes it, and it's covered at two
   levels: a fast unit test
   (`tests/test_streaming_generator_lifecycle.py`, no database, asserts
   `.aclose()` closes the wrapped sync generator) and a multi-connection
   integration test
   (`TestGeneratorCloseCleanup::test_closing_the_route_level_generator_early_returns_its_session_to_the_pool`,
   real database, real `session_scope`, checks the actual pool/lock/
   transaction state).
3. **There is still no genuine client-disconnect *detection* wired into the
   orchestrator itself** (`is_disconnected=lambda: False` in
   `app/api/v1/conversations.py`) — deferred, since only the
   effectively-instant mock provider is enabled and the cost of finishing a
   turn's *business logic* server-side after a disconnect is currently
   negligible. This is independent of session cleanup, which is now
   guaranteed regardless: a disconnect mid-turn correctly persists only
   what had already committed (e.g. the user's message, if the turn hadn't
   reached the assistant-message phase yet) and releases the session
   promptly — verified live by disconnecting mid-turn and confirming the
   conversation was left with exactly the user message, no orphaned
   assistant message, and zero lingering locks or idle transactions
   afterward. A real, network-bound provider in a later phase should still
   thread a real disconnect check through the orchestrator, to stop wasting
   provider-call time/cost after a disconnect — that part remains
   deferred; session-lifecycle safety does not.
4. A disconnect exactly during a `response.error` event is the one case
   where something isn't recorded: `_persist_failure`'s `last_error_code`
   write happens *after* that yield, so it's skipped if the generator is
   closed at exactly that point — harmless, since the conversation is left
   `active` and safely retryable, just without that one diagnostic field
   set.

### Provider abstraction

Every provider (`app/ai/providers/base.py`) implements the same contract:
typed request/response objects, `generate()` (complete response),
`stream()` (chunked), tool-call requests, usage metadata, a finish reason,
and controlled errors — no provider-specific type ever leaks into the
orchestrator or an API response. `MockProvider` is the only one enabled by
default; `OpenAIProvider`/`AnthropicProvider` raise a controlled
`ProviderConfigurationError` (never a silent fallback) unless their API key
is configured. `get_provider(settings)` is the single selection point and
rejects an unknown `AI_PROVIDER` value the same way.

### Grounding, tools, qualification, safety

Retrieval, tool execution, qualification extraction, and safety evaluation
are each independent, unit-tested modules the orchestrator calls in
sequence — not inlined into one large function. See docs/api.md for the SSE
event contract and docs/security.md for the safety engine, prompt-injection
resistance, and system-instruction boundary in detail.

## Public embeddable widget (implemented — Phase 5)

### Extending, not duplicating, the Phase 4 engine

The public widget conversation routes (`app/api/v1/widget_public.py`) reuse
`ConversationOrchestrator` — no separate "widget orchestrator" class exists,
and `submit_message`, its transaction phasing, its row-locking, and its SSE
event shapes are untouched. **`orchestrator.py` was not left byte-for-byte
unchanged, however**: `start_conversation` gained two optional keyword
parameters,
`mode: ConversationMode = ConversationMode.TEST` and
`channel: ConversationChannel = ConversationChannel.DASHBOARD_TEST`,
matching the Phase 4 defaults exactly. This is a backward-compatible
signature extension, not a rewrite — the dashboard test-console's call site
(`app/api/v1/conversations.py`) does not pass either argument and is
therefore unaffected, which is asserted, not just claimed: the full Phase 4
`test_conversations_api.py` suite and the `multiconn` PostgreSQL
integration suite both still pass after this change (see
docs/PROGRESS.md's Phase 5 verification results). The widget route is the
only caller that passes `mode=ConversationMode.WIDGET,
channel=ConversationChannel.WIDGET` explicitly. The `stream_sync_generator`
SSE adapter (`app/api/v1/conversations.py`) genuinely is unchanged — the
widget's message-send route imports and calls it directly, following the
identical `session_scope_factory`-owned-session pattern documented above
for the dashboard route, not a re-implementation of it.

### A parallel, deliberately separate authorization model

The dashboard's `TenantContext` (resolved from a Bearer JWT + tenant
membership) has no equivalent identity to resolve for a public widget
caller — there is no user, no login. `app/api/widget_deps.py` builds an
analogous but distinct `WidgetVisitorContext`, resolved instead from
`public_id` (path) + a capability token (header), never from a JWT. Two
resolution shapes exist because two different route shapes need them: one
where `conversation_id` is in the URL (`get_widget_visitor_context`, cross-
checks the token matches) and one where it isn't
(`get_widget_visitor_context_from_token`, for `/contacts`,
`/appointment-requests`, `/handoff-requests` — the token alone determines
the conversation, since a session is always 1:1 with one). Full security
model: docs/security.md.

### New repository query functions, not new repository methods, for the two "resolve before I know the tenant" lookups

`get_installation_by_public_id` (`app/repositories/widget_installation.py`)
and `get_session_by_token_hash` (`app/repositories/widget_visitor_session.py`)
are plain module-level functions, not `TenantScopedRepository` methods — a
deliberate choice made after noticing that constructing a
`TenantScopedRepository` with a fabricated placeholder `tenant_id` just to
reach `self.db` would leave a half-valid repository object sitting around
that *looks* safe to reuse for a tenant-scoped call but silently isn't
(every subsequent `.get()`/`.list()` on it would filter by the fake ID and
silently return nothing, rather than erroring). A plain function makes the
"this lookup is not yet tenant-scoped, by necessity" fact visible at the
call site instead of hidden behind a class that implies scoping everywhere
else in the codebase.

### Rate limiting as a Protocol, not a concrete dependency

`app/core/rate_limit.RateLimiter` is a `Protocol` with one shipped
implementation (`InMemoryRateLimiter`, single-process, documented in
docs/security.md); `app/api/widget_deps.rate_limit(action, limit=...,
window_seconds=...)` is a dependency *factory* returning a per-route
dependency, so each public route declares its own limit inline
(`Depends(rate_limit("message", limit=30, window_seconds=60))`) rather than
one shared global limit. A future Redis-backed implementation only needs to
satisfy the same three-method `Protocol` — no call site changes.

### A separate CORS policy, not a relaxed one

`app/core/widget_cors.WidgetPublicCorsMiddleware` exists because the
dashboard's fixed-origin, credentialed `CORSMiddleware` (`app/main.py`) is
structurally wrong for a surface meant to run on arbitrary third-party
domains unknown until runtime — not because the widget needed *weaker*
CORS, but because it needed a *different shape* of CORS (reflected origin,
zero credentials, since the widget never uses cookies). Middleware
ordering matters here and was confirmed empirically, not assumed
(`app.add_middleware()`'s most-recently-added middleware ends up
outermost) — full incident writeup, including a credential-leakage bug this
surfaced, in docs/security.md.

### Widget bundle (`widget/`)

A separate, dependency-free TypeScript package, bundled with esbuild into
one minified IIFE (`widget/dist/widget.js`, ~25KB) — no React, no framework,
no runtime dependency at all beyond the browser itself. Structure:

- `src/index.ts` — the self-initializing entry point. Reads
  `document.currentScript`'s `data-receptionist-id`/`data-api-base-url`
  attributes **synchronously**, before any `await` — the one point in an
  `async`-loaded script's lifetime `document.currentScript` is guaranteed to
  still resolve to its own tag. A module-level `Map` keyed by `public_id`
  (`window.__aiReceptionistWidget`) prevents double-initialization if the
  snippet is somehow present twice on one page.
- `src/ui.ts` — the `Widget` class: owns one Shadow DOM root (`mode: "open"`,
  attached to a single host `<div>`), all panel/launcher/transcript/form
  rendering, and the conversation/voice/form state machine. Nothing outside
  its own shadow root or host element is ever touched.
- `src/api.ts` — a thin fetch-based client for the 8 public routes plus the
  same hand-rolled SSE line parser pattern as the dashboard's
  `conversations-api.ts` (native `EventSource` can't carry the
  `X-Widget-Session-Token` header, so both clients read the POST response
  body as a stream directly).
- `src/voice.ts` — `VoiceRecognizer`/`VoiceSpeaker` wrapping
  `SpeechRecognition`/`speechSynthesis` with feature detection; see
  docs/security.md for what this does and does not claim about where
  speech processing happens.
- `src/storage.ts` — `sessionStorage`-backed capability-token persistence,
  scoped per `public_id`, degrading to a no-op (fresh session every time)
  if storage is unavailable rather than throwing.
- `src/styles.ts` — the complete CSS injected into the shadow root as a
  `<style>` tag; nothing styles the widget from outside its shadow
  boundary, and the widget's own styles cannot leak onto the host page.

**A real CSS bug found via live browser testing, not the unit suite:**
`.error-banner { display: flex; ... }` and the element's own `hidden`
attribute have equal CSS specificity (`.error-banner` vs. the UA
stylesheet's `[hidden]` rule), and source order let the class win — a
"hidden" error banner rendered visibly (as an empty colored bar) in a real
browser despite `element.hidden === true`. jsdom-based component tests
never caught this because they assert on the `hidden` *property*, not on
computed `display`. Fixed by adding an explicit
`.error-banner[hidden] { display: none; }` rule (higher specificity than
either alone), matching the pattern `.panel[hidden]` already used. A second,
related bug the same live session found: a form's own validation error
(`showError`, writing to the *main* conversation error banner) was
invisible while a structured action form was open, because
`.form-overlay { position: absolute; inset: 0; }` visually covers that
banner completely — fixed by giving each form overlay its own local
`.form-error` element instead of sharing the main banner, with a
regression test (`ui.test.ts`) asserting the error appears inside the
overlay and the main banner stays hidden.

Full widget, security, and live end-to-end verification results:
docs/PROGRESS.md.

### Structured service/location pickers (Phase 5 follow-up)

The public config response (`GET .../config`) gained `services`/`locations`
arrays — active-only, public-safe (`id`/`name`/`description` for services,
`id`/`name`/`timezone` for locations) — and the widget's appointment form
renders a `<select>` for each only when its array is non-empty, always with
a "Not sure" (empty-value) first option. Submission re-validates both IDs
server-side exactly like every other client-supplied identifier in this
codebase: same-tenant (`ServiceRepository`/`BusinessLocationRepository`,
tenant-scoped by construction), active-only (`get_active`, added
alongside `get`), and — the one relationship a flat FK can't express —
that a service restricted to one location (`Service.location_id` set)
isn't requested with a *different* location. When a location is selected,
its own IANA timezone governs the appointment date's "today" boundary
server-side (`app/services/appointment_request_service.py`), not the
visitor's browser clock or an unvalidated free-text timezone string — the
widget also sends that location's timezone as the request's `timezone`
field, so the date picker and the server's validation reasoning stay about
the same "today." Regression coverage: `tests/test_appointment_request_service.py`
(17 tests, including a clock-frozen proof that the location's timezone
overrides a deliberately different submitted one) and
`tests/test_widget_public_api.py`.

### Live local dashboard preview (Phase 5 follow-up)

`/dashboard/receptionist/widget`'s preview is the **real** embeddable
widget bundle against the **real** public API — not a mock, and not a
second "preview mode" branch inside the widget's own code:

- The dashboard renders `<iframe src="/widget-preview.html?publicId=...&apiBaseUrl=...&bundleUrl=...&sessionNamespace=...">`,
  sandboxed with `allow-scripts allow-same-origin allow-forms` (no
  `allow-top-navigation`, `allow-popups`, etc.).
  `widget-preview.html` (`frontend/public/`) is a small, static,
  dependency-free page — no dashboard code, no import of `lib/api.ts`, no
  reference to the access token or either auth cookie anywhere in it — that
  reads those query parameters and injects the *exact same*
  `<script data-receptionist-id=... async>` snippet a real customer page
  would use, sourced from the installation's real `widget_bundle_url`.
- **Origin trust, not domain-list pollution**: the preview page is served
  from the dashboard's own origin, which the backend trusts via a
  dedicated, separate setting (`Settings.platform_preview_origins`, see
  `app/api/widget_deps.validate_widget_origin`) — never by adding that
  origin to the tenant's own `WidgetInstallation.allowed_domains`, which
  would incorrectly make the dashboard itself a permanently-"allowed" real
  embedding domain for that tenant.
- **No dashboard credential reaches the widget** — not by a special
  precaution added for preview, but because the widget bundle already
  never does the things that would leak one: it never reads
  `document.cookie`, never reaches into `window.parent`, and every one of
  its `fetch()` calls omits `credentials: "include"` (default
  `"same-origin"`), so even the dashboard's own HttpOnly refresh cookie —
  scoped to a *different* origin (the backend) regardless — is never sent.
  The preview iframe's sandboxing is defense-in-depth on top of that, not
  the only thing preventing it.
- **The same capability-token flow, unmodified**: `POST .../sessions` still
  issues an opaque token the preview's widget instance stores in its own
  `sessionStorage` exactly like a real visitor's browser would — there is
  no bypass, shortcut, or elevated-trust code path for preview traffic at
  the API layer.
- **Preview traffic is tagged, not silently indistinguishable from real
  visitors**: the injected snippet carries `data-visitor-reference="dashboard-preview"`,
  threaded through to `Conversation.visitor_reference` on every session the
  preview starts (an additive use of a field that already existed) — a
  tenant reviewing their records can tell preview conversations apart from
  real ones.
- **"Restart preview"** doesn't reload the widget bundle or touch the
  backend at all — reloading the iframe alone would *not* be enough, since
  `sessionStorage` persists across same-origin frame reloads for the life
  of the tab, so the old conversation would simply resume. Instead, the
  dashboard generates a fresh random `sessionNamespace` and remounts the
  iframe with it (React `key`); the widget threads that namespace into its
  `sessionStorage` key (`widget/src/storage.ts`), so a new namespace is, by
  itself, enough to make the lookup miss and start a genuinely new session
  — no explicit clearing, no reaching into the iframe from outside it.
- The live preview only renders for an **active** installation (the same
  `409` a real embed would get from `draft`/`paused` otherwise) — a draft
  or paused installation shows a plain "activate to preview" message
  instead of a non-functional iframe.

Regression coverage: `frontend/src/app/dashboard/receptionist/widget/page.test.tsx`
("live local preview" describe block — activation-gating, real bundle/config
URL construction, sandbox attributes, and restart-changes-the-src) and
`tests/test_widget_public_api.py::TestWidgetConfig::test_platform_preview_origin_is_always_allowed`.

## Client operations dashboard (implemented — Phase 6)

Everything below is new in Phase 6: a full operations surface over the data
Phase 4/5 already capture — conversations, contacts, enquiries,
appointments, and handoffs — plus internal notes, an audit log, and
tenant-scoped analytics. Nothing here required a new external service; it
runs entirely on the existing Postgres database, the existing mock AI
provider, and the existing FastAPI/Next.js stack.

### Source classification is server-verified, not client-claimed

The dashboard needs to distinguish three kinds of conversation: genuine
visitor traffic (`widget`), the dashboard's own live local preview
(`preview`), and the private test console (`test`). `test` is trivial
(`Conversation.mode == TEST`, set server-side, never client-chosen). The
`widget`/`preview` distinction reuses the Phase 5 follow-up's platform-
preview-origin check: `WidgetVisitorSession.is_platform_preview` is set at
session-creation time from the request's own `Origin` header against
`Settings.platform_preview_origins_list` — never from
`visitor_reference` or any other client-supplied field, so a real
customer's widget embed cannot spoof either direction. One function,
`app/core/conversation_source.py::source_case_expression` (and its Python
twin, `classify`), is the single place this logic lives — the conversation
list, conversation detail, and every analytics aggregate all call it,
so the same conversation is never classified two different ways in two
different places. `unique_visitor_sessions` is currently numerically
identical to `genuine_widget_conversations + preview_conversations`
because a `WidgetVisitorSession` is 1:1 with the conversation it
authorizes today — exposed as its own metric anyway since a future phase
could let one session span multiple conversations.

### Analytics: explicit aggregates, never a loaded transcript

`app/services/analytics_service.py` computes every overview/timeseries
number via a small, fixed number of `SELECT COUNT/AVG ... FILTER (WHERE
...)` queries — never by loading every row of a list and counting in
Python, and never one query per day for the timeseries (three queries
total, each `GROUP BY` a `date_trunc`-style bucket, cover the whole
requested range). The module's own docstring is the canonical numerator/
denominator definition for every metric; see it for the full accounting.
Two points worth calling out here:

- **Estimated staff time saved is a single, global, configurable
  assumption** (`Settings.estimated_staff_minutes_per_conversation`,
  default 5.0 minutes) multiplied by the genuine-widget-conversation
  count for the period — it has no per-tenant empirical basis, is always
  labeled an estimate (`estimated_staff_time_saved_minutes_is_estimate:
  true` in the API response, and in the UI), and is never described as
  revenue.
- **"Unanswered / fallback responses" is currently mock-provider-only.**
  The signal is part of the provider-independent contract
  (`GenerateResult`/`StreamChunk.is_fallback` in
  `app/ai/providers/base.py`), so any future real-LLM provider *can*
  populate it — but only `MockProvider` currently does, by checking its
  own composed response text against a small, explicit set of "found
  nothing" markers (`app/ai/providers/mock.py::FALLBACK_RESPONSE_MARKERS`).
  This is documented as a known limitation, not silently glossed over: the
  metric will always read `0` for a tenant using a non-mock provider until
  that provider implements its own truthful signal.

Every count-based metric defaults to **excluding** `test`/`preview`
sources; callers pass `include_test_preview=true` to see all three
combined. The three source counts are always broken out individually
regardless, so the excluded volume stays visible even in the default view.
Date-range presets (`today`/`7d`/`30d`/`custom`) are resolved as whole
calendar days in the **tenant's own timezone**
(`Tenant.timezone`, already a Phase 1 field) and converted to UTC bounds
before touching the database — Postgres never does timezone arithmetic
itself. A custom range is capped at `Settings.analytics_max_range_days`
(366 days by default) so a client cannot request an unbounded scan.

**Analytics performance and the future pre-aggregation boundary**: every
overview/timeseries call computes its numbers live, on request, via the
aggregate queries described above — there is no cache, materialized view,
or background rollup job. `tests/test_dashboard_performance.py` asserts
the endpoint issues a small, fixed number of queries; the Phase 6
follow-up round additionally measured this directly against a real local
Postgres instance with a throwaway tenant seeded at two volumes (500 and
8,000 conversations, each with a realistic share of messages, contacts,
enquiries, appointment requests, and handoffs), counting actual SQL
statements via a SQLAlchemy `before_cursor_execute` listener rather than
inferring it from code review:

| Endpoint | Queries (constant, 500 vs. 8,000 conversations) | Wall time @ 500 | Wall time @ 8,000 |
|---|---|---|---|
| `GET .../analytics/overview` | 9 (1 tenant-timezone lookup + 8 aggregate queries — see `analytics_service.get_overview`'s numbered comments) | 281 ms | 208 ms |
| `GET .../conversations` (list, page 1) | 3 (1 tenant-timezone lookup + `COUNT` + paginated `SELECT`) | 36 ms | 32 ms |
| `GET .../enquiries` (list, page 1) | 3 (same shape) | 11 ms | 9 ms |

Query count was confirmed identical at both volumes — the fixed-query-count
claim is measured, not assumed. Wall time did **not** measurably increase
with the 16x row-volume increase at this scale, and did not decrease
monotonically either (281ms → 208ms includes normal local-Postgres cache
warm-up noise between runs, not a real trend) — both are well under any
perceptible latency budget at these volumes. `EXPLAIN (ANALYZE, BUFFERS)`
against the 8,000-row volume confirmed every one of these queries uses the
existing single-column `tenant_id` index (`ix_conversations_tenant_id`,
`ix_enquiries_tenant_id`) — **no sequential scan occurred at this volume**.
However, the date-range bound (`started_at`/`created_at`) is applied as a
post-scan `Filter`, not a second index condition, because there is no
composite `(tenant_id, started_at)` index — the planner scans every row
for the tenant via the `tenant_id` index, then filters by date in memory.
This is invisible at hundreds or low thousands of rows per tenant (172
buffer pages read, sub-6ms execution time even at 8,000 rows in this test)
but is the concrete mechanism behind the "large tenant" ceiling: **a single
tenant accumulating conversation volume such that its own row count no
longer fits comfortably in a handful of buffer pages** is what will
eventually make this Filter step, not the aggregate itself, the slow part
— independent of how many *other* tenants exist, since every query is
already `tenant_id`-scoped. This local, single-machine, single-tenant
8,000-row measurement is **not** a production-scale benchmark (real
concurrent load, connection contention, a much larger and fuller buffer
cache, and true multi-tenant row distribution are all untested here) — it
demonstrates the query shape is fixed-count and index-scan-based at this
scale, nothing more. At that point, a future phase should add either a
composite `(tenant_id, started_at)` / `(tenant_id, created_at)` index (the
cheapest first step, before reaching for pre-aggregation) or, once even
that stops being enough, a scheduled daily/hourly rollup table
(pre-aggregated counts per tenant/receptionist/day, computed by a
background job, with the overview endpoint reading from it instead of the
raw tables) or a materialized view refreshed on the same cadence. Nothing
about the current API contract (the `AnalyticsOverviewResponse`/
`TimeseriesPoint` shapes) would need to change for either migration — only
what backs `get_overview`/`get_timeseries` internally.

### Optimistic concurrency and the atomic handoff claim

Enquiries, appointment requests, and human handoffs each carry a `version`
integer. Every status-change endpoint requires the caller to supply the
`version` it last read; `app/services/concurrency.py::apply_versioned_update`
applies the change via one `UPDATE ... WHERE id = ? AND version = ?`
statement that also increments `version` — a stale version means the
`UPDATE` matches zero rows, which the helper turns into a
`VersionConflictError` (409). This is deliberately simpler than optimistic-
locking schemes that re-read after a conflict: the dashboard's response is
just "reload and try again," never a silent merge.

Claiming a handoff has a stricter requirement than "don't overwrite a
stale read" — two tenant members can click "claim" at the *same* open
handoff at the *same* moment, and at most one may win, with no window
where both could succeed. `HumanHandoffRepository.claim_atomically` uses a
single conditional `UPDATE human_handoffs SET status = 'claimed', ... WHERE
id = ? AND status = 'open'` — never a `SELECT` followed by a check followed
by a separate `UPDATE`, which would leave exactly the race window this
exists to close. `human_handoff_service.update_status()` (resolve/cancel)
deliberately refuses `CLAIMED` as a target for this same reason: routing
that transition through the generic version-checked path would reintroduce
the race `claim()` exists to avoid.

This was verified against genuinely separate database connections, not
just a single already-serialized test session — see
`tests/integration/test_handoff_claim_concurrency.py` (`pytest -m
multiconn`), which drives two real HTTP requests from two real tenant
members through a `ThreadPoolExecutor`, exactly mirroring the pattern
`tests/integration/test_conversation_concurrency.py` established in Phase 4
for the same reason: `tests/conftest.py`'s shared-session fixture collapses
what would be independently-pooled connections in production into one,
which would hide a race like this entirely.

### Internal notes: typed foreign keys, not a polymorphic pair

`InternalNote` attaches to exactly one of five entity types
(conversation/contact/enquiry/appointment_request/human_handoff) via five
nullable, typed foreign keys — each `ON DELETE CASCADE` to its own parent
table — rather than a generic `(entity_type: str, entity_id: uuid)` pair.
A plain FK gives real referential integrity a polymorphic pair cannot (a
note can never dangle after its parent is deleted, and the database itself
rejects a reference to a nonexistent row); a `CHECK (num_nonnulls(...) =
1)` constraint enforces "exactly one target." The service layer
(`app/services/notes_service.py`) additionally verifies the target exists
*for this tenant specifically* — using the exact same tenant-scoped
repository every other route uses for that resource — before creating a
note, since a plain FK to e.g. `enquiries.id` is not itself tenant-composite
and so cannot reject a cross-tenant reference at the database level on its
own. Notes are never read by the AI orchestrator and never served by any
public-widget route.

### Activity log: append-only, no FK to the entity it describes

`ActivityEvent` is written only through
`app/services/activity_service.py::record` — no route creates, edits, or
deletes one directly. `entity_id` is deliberately a plain UUID with no
foreign key: an audit record must remain readable even after the row it
describes is later deleted (e.g. a cascade-deleted conversation), which a
FK would prevent. `event_metadata` is restricted by convention (enforced
in code review, the same way every other "never log this" rule in this
codebase is) to small, safe fields such as an old/new status pair — never
a secret, token hash, password, or full message/transcript body.

### Role permissions: two dependencies, not scattered checks

Every dashboard route reuses the Phase 2 `require_tenant_role(minimum)`
dependency factory — there is no new permission-check mechanism. The
policy: any active tenant member may view every resource and take the
day-to-day operational actions (update an enquiry's status, claim or
resolve a handoff, add or edit their own notes); confirming/declining/
cancelling an appointment, cancelling a handoff, exporting data, and
deleting another member's note require `admin` or `owner`. The one
handoff-specific rule (member may resolve but not cancel) is expressed as
a single explicit role check in `app/api/v1/dashboard_records.py`, not a
new dependency, since it is the only asymmetric case in the whole surface.
See docs/security.md's permission matrix for the complete table.

### Dashboard shell

`frontend/src/app/dashboard/layout.tsx` is a single Next.js App Router
layout wrapping every route under `/dashboard` exactly once — Overview,
Conversations, Contacts, Enquiries, Appointments, Handoffs, Activity,
Settings (all seven pages), the private test console, and widget
installation management. It renders `DashboardShell`
(`frontend/src/components/dashboard/DashboardShell.tsx`), which owns the
auth/loading/redirect boilerplate, tenant identity and role, main
navigation with active-route highlighting (a single ten-item nav list,
not a page tier plus an overflow "more" menu — Settings, the test
console, and widget management are direct top-level links, not
menu-only), and a responsive mobile drawer using the same nav list. Pages
no longer receive shell state via a render-prop; they call
`useDashboardContext()` (`frontend/src/components/dashboard/
DashboardContext.tsx`), a React context populated once by the layout,
which throws if called outside it — a programming-error guard, not a
runtime user-facing state, since the layout never renders `children`
until auth has resolved.

This replaced Phase 6's original per-page `<DashboardShell
title="X">{({tenantId}) => ...}</DashboardShell>` render-prop wrapper,
which the Phase 6 follow-up round's gap review found produced a shell
duplicated per page rather than a single shared instance, and which
never covered the settings/test-console/widget pages at all (they kept
separate, inconsistent layouts). `SettingsShell`
(`frontend/src/app/dashboard/settings/SettingsShell.tsx`) deliberately
kept its own render-prop API unchanged (`children({tenantId, canEdit})`)
— it now reads `useDashboardContext()` internally instead of `useAuth()`
directly — so its 7 existing consumer pages needed zero code changes.
The private test console and widget-management pages were rewritten to
read `useDashboardContext()` directly and dropped their own
auth-loading/redirect/back-link boilerplate, since the layout now
supplies all of it once. (Phase 7 later moved this file to
`frontend/src/app/(app)/dashboard/settings/SettingsShell.tsx` — see
below; the component itself was untouched by that move.)

## Public marketing website & interactive demos (implemented — Phase 7)

### Two route groups, not one layout with conditionals

`frontend/src/app/` now has two Next.js route groups sitting side by side:
`(marketing)` (16 public routes) and `(app)` (`login`, `register`,
`onboarding`, `dashboard` — everything Phase 2-6 already built, moved
here unchanged). The root layout (`frontend/src/app/layout.tsx`) no
longer wraps anything in `<AuthProvider>`; that now lives entirely in
`frontend/src/app/(app)/layout.tsx`. This was not a stylistic choice —
Phase 7's live testing found the root layout firing an unconditional
`auth/refresh` call (and a correctly-rejected `403`, since no dashboard
session exists) on every public page load, violating both "no
unnecessary backend calls on a static page" and "the public site never
receives a dashboard cookie." A route-group split, not a conditional
inside a shared layout, was the fix, because Next.js route groups don't
add a URL segment — `(marketing)/page.tsx` still serves `/`, and
`(app)/dashboard/page.tsx` still serves `/dashboard` — so no existing URL
changed. `frontend/src/app/(marketing)/layout.tsx` wraps every public
route in a skip-link, the shared `Header`/`Footer`, and nothing else —
no auth, no dashboard context, no widget/auth module import anywhere in
its dependency tree.

### Centralized configuration, not scattered literals

Four small modules under `frontend/src/lib/` are the single source of
truth for everything a future rebrand/re-pricing/re-domain would touch:
`brand.ts` (product name, tagline, description, support email, CTA
labels — the final brand name has not been chosen, so every page reads
`brand.productName` rather than a hardcoded string), `pricing.ts` (three
plans, every price explicitly flagged `isPlaceholder: true`; `Scale` uses
`monthlyPriceUsd: null` → "Contact us" rather than a speculative number),
`demos.ts` (the three demo tenants' `publicId`/business name/suggested
questions/safety note — the single place a demo's `publicId` must match
the backend seed), and `seo.ts` (`getSiteUrl()` reads
`NEXT_PUBLIC_SITE_URL`, defaulting safely to `http://localhost:3000`;
`buildMetadata()`/`organizationJsonLd()`/`faqJsonLd()`/
`breadcrumbJsonLd()` are the only place canonical URLs and structured
data are constructed).

### Demo tenants: real rows, not a parallel demo system

The three interactive demos (`/demo/clinic`, `/demo/hotel`,
`/demo/real-estate`) are not a separate mock subsystem — each is a real
`Tenant` row with a real, industry-templated `Receptionist` and a real
`ACTIVE` `WidgetInstallation`, seeded by
`backend/app/seed_data/public_demo_tenants.py` (idempotent, keyed on a
fixed `slug`) and reusing `onboarding_service.select_industry()` /
`apply_template_defaults()` exactly as a real tenant's onboarding flow
does — so qualification fields, suggested questions, and safety rules are
all industry-template-derived, not hand-authored per demo. The one
deliberate departure from `app/seed_data/demo_tenants.py` (Phase 3's
internal, login-based dashboard-exploration demos): these three tenants
have **no `User` and no `TenantMember` row at all**, because the public
widget API (Phase 5) never required a dashboard login in the first
place — "if demo users are unnecessary, do not create them." Each
`WidgetInstallation.public_id` is a fixed, memorable string
(`demo-clinic-sunrise`, `demo-hotel-azurebay`, `demo-realestate-falcon`)
rather than the usual random `secrets.token_urlsafe(24)` — safe because
`public_id` was never a secret by design (see its docstring), and a
fixed value is what lets `frontend/src/lib/demos.ts` reference it
directly without a runtime lookup.

### Reusing, not reimplementing, Phase 5's live-preview mechanism

`frontend/public/demo-widget.html` is `widget-preview.html` (Phase 5's
dashboard live-preview page) adapted for public use: same
query-param-driven config (`publicId`/`apiBaseUrl`/`bundleUrl`/
`sessionNamespace`), same sandboxed-iframe embedding
(`allow-scripts allow-same-origin allow-forms`), same trust path (served
from the marketing site's own origin, already a trusted
`platform_preview_origins` entry), same zero-dependency static page with
no import of any dashboard/auth code. The only difference is the visible
banner text and `data-visitor-reference` value
(`"public-demo"` vs. `"dashboard-preview"`) — the classification that
excludes this traffic from tenant analytics (`is_platform_preview`, see
Phase 6 above) depends only on the `Origin` header, not on this label,
so demo traffic is excluded from "production" analytics with zero new
backend code. `DemoWidgetEmbed`
(`frontend/src/components/marketing/DemoWidgetEmbed.tsx`) is the React
wrapper: it generates `sessionNamespace` inside a `useEffect` — never
during the initial render, which Next.js also executes server-side for a
Client Component, where a `crypto.randomUUID()` call would produce a
different value than the client's own hydration pass and trigger a
hydration-mismatch error (found via live testing; see docs/PROGRESS.md)
— and remounts the iframe under a new React `key` on "Restart demo,"
which is what actually starts a genuinely new, isolated conversation
rather than merely clearing the visible transcript.

### Public leads: a global model, deliberately not a synthetic tenant

`PublicLead` (`app/models/public_lead.py`) follows the one existing
precedent for platform-level (not customer-owned) data,
`IndustryTemplate`: a plain model with no `tenant_id` column at all. The
alternative — inventing a "platform tenant" so the existing
`TenantContext`/`require_tenant_role` machinery could be reused — was
rejected because a lead is not yet a customer, and forcing one into a
tenant row would be a worse data model for a problem `IndustryTemplate`
already solved correctly. The endpoint
(`app/api/v1/public_leads.py`) is intentionally the simplest possible
shape: one `POST`, no `GET`, reusing Phase 3's plain-text validation
policy and a new IP-only-keyed variant of the existing
`app/core/rate_limit.py` dependency (the widget's version keys on an
installation, which doesn't exist for this route).
