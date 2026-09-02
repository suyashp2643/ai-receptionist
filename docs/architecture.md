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
