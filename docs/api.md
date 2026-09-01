# API Reference (Phase 2)

Base path: `/api/v1`. Full interactive docs at `/docs` (Swagger UI) when the
backend is running. See `docs/security.md` for the auth/CSRF model these
routes rely on.

## Health

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/health` | none | Also mounted here, identical to below |
| GET | `/api/v1/health` | none | Reports `status`, `service`, `environment`, `database.{status,detail}` |

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
length / invalid email / unknown timezone.

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

## Error shape

Every error response (from `app/core/errors.py`) has the same shape:
```json
{ "error": { "message": "...", "status_code": 404 } }
```
(422 validation errors additionally include `"details": [...]` — the raw
Pydantic error list.)

## Not implemented in Phase 2

Invitation delivery (email invites), receptionist configuration, knowledge,
conversations, appointments, analytics, and any Revenue Brain / AI Sales
Employee integration — all later, explicitly-approved phases.
