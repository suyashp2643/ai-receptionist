# Security

## Authentication flow

Email/password only in the MVP (no magic links, no OAuth yet).

1. **Register** (`POST /api/v1/auth/register`): email is normalized
   (trimmed + lowercased), password is hashed with Argon2id
   (`argon2-cffi`), and — atomically, in one DB transaction — a `User`, a
   `Tenant`, and the user's `owner` `TenantMember` row are created. Any
   failure (including a duplicate email, caught via the `users.normalized_email`
   unique constraint) rolls back everything; nothing partial is ever left
   behind. A session is issued immediately (see Token lifecycle).
2. **Login** (`POST /api/v1/auth/login`): normalizes the email, verifies the
   Argon2id hash. If the email doesn't exist, a dummy Argon2 verification
   still runs (`run_dummy_password_verification`) so response timing doesn't
   reveal account existence. Wrong password, unknown email, and inactive
   accounts all return the same generic `401 Invalid email or password.` —
   never a distinguishing message.
3. **Refresh** (`POST /api/v1/auth/refresh`): rotates the opaque refresh
   token (see below) and issues a new access token.
4. **Logout** (`POST /api/v1/auth/logout`): revokes the current refresh
   token's entire family and clears both auth cookies.
5. **`GET /api/v1/auth/me`**: returns the authenticated user + their tenant
   memberships, resolved fresh from the database on every call.

## Token lifecycle

Two distinct token types, deliberately different in shape and lifetime:

| | Access token | Refresh token |
|---|---|---|
| Format | JWT (HS256) | Opaque random (`secrets.token_urlsafe(32)`, 256 bits) |
| Lifetime | 15 min (`ACCESS_TOKEN_TTL_MINUTES`) | 30 days (`REFRESH_TOKEN_TTL_DAYS`) |
| Storage (server) | Not stored — stateless | SHA-256 hash only, in `refresh_tokens` |
| Storage (client) | In-memory (React state) | `HttpOnly` cookie |
| Claims | `sub` (user id), `sid` (session/family id), `iat`, `exp`, `iss`, `aud` | N/A (opaque) |

**Why a JWT for access but not refresh:** the access token is short-lived
and stateless by design — no DB lookup needed to validate it on every
request, only a signature + claims check (algorithm is whitelisted to
`HS256` on decode, preventing algorithm-confusion attacks; `iss`/`aud` are
validated too). The refresh token is long-lived and must be revocable
server-side at any time (logout, theft detection), which a self-contained
JWT cannot do without an additional server-side blocklist — an opaque
random value with a DB-backed hash is simpler and strictly more secure for
that purpose.

**Rotation and reuse detection:** every successful refresh creates a new
`refresh_tokens` row in the same `family_id` and marks the old row
`revoked_at` + `replaced_by_token_id`. If an already-revoked token is ever
presented again — the signature of a stolen or replayed token — the
**entire family** is revoked immediately (`RefreshTokenRepository.revoke_family`),
forcing full re-authentication. This is tested explicitly
(`test_refresh_token_reuse_revokes_entire_family`).

## Cookie behavior

Two cookies, both scoped to `Path=/api/v1/auth` (never sent to ordinary API
routes):

- **Refresh cookie** (`ai_receptionist_refresh`): `HttpOnly`, so JavaScript
  cannot read it (mitigates XSS token theft). `SameSite=Lax` — safe for
  local dev because `localhost:3000` and `localhost:8000` are *same-site*
  (SameSite is scoped by scheme + registrable domain, not port) despite
  being different origins. `Secure` is environment-aware: on unless
  `ENVIRONMENT=development` (or explicitly overridden via `COOKIE_SECURE`),
  so local HTTP development works without weakening the production default.
- **CSRF cookie** (`ai_receptionist_csrf`): deliberately **not** `HttpOnly`
  — the frontend must read it to echo it back as a header (see below). It
  is stable for the life of a session (refresh/logout re-set it with the
  same value rather than rotating it — there's no security benefit to
  rotating a CSRF token, unlike the refresh token itself).

Both are cleared (`Max-Age=0`) on logout and on any failed
refresh (invalid or reused token).

## CSRF defense

Double-submit cookie pattern, applied only to the two cookie-authenticated,
state-changing routes: `/auth/refresh` and `/auth/logout`. A request must
present the CSRF cookie's value again as an `X-CSRF-Token` header; the
dependency (`app/core/csrf.py`) does a constant-time comparison
(`hmac.compare_digest`) and returns `403` on any mismatch or absence.

Every other authenticated route uses the `Authorization: Bearer <token>`
header, which browsers never attach automatically cross-site — those routes
are not CSRF-exploitable by construction and don't need this defense.

CORS is configured with an explicit origin allow-list (`CORS_ALLOW_ORIGINS`,
default `http://localhost:3000`) and `allow_credentials=True` — never a
wildcard `*` origin combined with credentials (browsers reject that
combination anyway, and it would be dangerous if they didn't). Tested in
`tests/test_cors.py`: an untrusted origin gets no
`Access-Control-Allow-Origin` header on simple requests and a `400` on
preflight.

## Tenant-context resolution

For any route containing `{tenant_id}`, `app/api/deps.get_tenant_context`:

1. Authenticates the caller via the access token (`get_current_user`).
2. Looks up `TenantMember` by `(tenant_id, user_id)` — **the `tenant_id`
   used is always the one in the URL path**, never a client-supplied body
   field or a JWT claim.
3. Requires `status == active`; otherwise (or if no membership row exists
   at all) returns `404 Tenant not found` — a non-member cannot distinguish
   "you're not allowed here" from "this doesn't exist."
4. Only then exposes `tenant_id`, `user_id`, and `role` to the route, as an
   immutable `TenantContext`.

Nothing here ever trusts a role, tenant ID, or membership status sent by
the client — see `test_client_supplied_role_cannot_elevate_privileges`.

## Permission model

Centralized in one place (`app/api/deps.require_tenant_role`) — route
handlers never contain their own `if role == "..."` checks. Roles are
ranked (`app/models/enums.ROLE_RANK`: `member` < `admin` < `owner`), and a
route declares only the *minimum* rank it needs:

| Route | Minimum role |
|---|---|
| `GET /tenants/{id}` | any active member |
| `PATCH /tenants/{id}` | `admin` |
| `GET /tenants/{id}/members` | `admin` |

A member with insufficient role gets `403`; a non-member gets `404` (see
above) — the two failure modes are intentionally distinct.

## Tenant-scoped repository

`app/repositories/base.TenantScopedRepository` is the pattern for any
future tenant-owned resource (FAQs, knowledge, conversations, etc. in later
phases): it is constructed with a `tenant_id` that must come from a
trusted `TenantContext`, and every `get`/`list`/`delete` it exposes filters
by that `tenant_id`. `get`/`delete` for a resource ID belonging to a
different tenant return `None`/`False` — never the resource, never an
error that would confirm the resource's existence.

`User` (global — not tenant-owned) and `Tenant` (the scoping root itself)
deliberately use their own plain repositories instead, so any place that
touches them without tenant filtering is explicit and grep-able rather than
hidden behind a shared abstraction.

## What was checked (security review)

| Check | Result |
|---|---|
| Plaintext passwords stored | No — Argon2id only (`app/core/security.py`) |
| Raw refresh tokens stored | No — SHA-256 hash only (`refresh_tokens.token_hash`) |
| Auth secrets committed | No — `JWT_SECRET_KEY` generated with `secrets.token_urlsafe(64)` directly into ignored `backend/.env`, never printed or logged |
| Sensitive values logged | No — structured logger never receives passwords/tokens/DSNs; `RefreshToken.__repr__` and `User.__repr__` deliberately omit hashes |
| Permissive production CORS | No — explicit origin allow-list, environment-configured |
| Wildcard credentialed origins | No — `allow_credentials=True` is only ever paired with the explicit origin list |
| Cross-tenant access | Blocked at the dependency layer + repository layer; covered by `tests/tenant_isolation/` (HTTP and repository level) |
| Client-controlled role escalation | Blocked — role is always read from `TenantMember`, never from the request; tested |
| Open redirect | N/A — no redirect endpoints exist in Phase 2 |
| JWT algorithm confusion | Mitigated — `algorithms=["HS256"]` whitelisted explicitly on every decode |
| Long-lived access tokens | No — 15-minute default, held in memory only, never `localStorage` |
| Refresh-token reuse | Detected and mitigated — whole family revoked on reuse |
| Real credentials in tracked files | No — verified via `git ls-files` + content grep before every commit; see `docs/PROGRESS.md` |

## How shared AI Business Engine authentication could replace this later

The auth surface is isolated behind three seams, each independently
replaceable without touching route/service code elsewhere:

1. **Token issuance/verification** (`app/core/security.py`): a future
   shared identity provider would just need to supply a compatible
   `decode_access_token`-shaped function (same `AccessTokenPayload` output)
   — `app/api/deps.get_current_user` doesn't care where the token came from.
2. **User storage** (`app/models/user.py`, `app/repositories/user.py`): if
   users become centrally managed, this repository's interface
   (`get_by_id`, `get_by_normalized_email`) is what a remote-identity-backed
   implementation would need to satisfy.
3. **Session/refresh mechanics** (`app/services/auth_service.py`): fully
   local today; a shared platform might instead delegate refresh/rotation
   to a central auth service, in which case only this module changes.

Tenant/membership/role logic (`TenantMember`, `require_tenant_role`,
`TenantScopedRepository`) is independent of all three and would not need to
change at all.
