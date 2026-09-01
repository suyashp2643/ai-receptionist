# Docker Setup (future — not runtime-tested)

Docker Desktop is not installed in the current development environment. The
`docker-compose.yml` at the repo root, and the `Dockerfile`s in `backend/`
and `frontend/`, were written for this future path and their **syntax only**
was validated (YAML parsed successfully with PyYAML; no `docker compose
config` or actual build/run was performed, since no Docker engine is
available here).

Do not treat this stack as verified until it has actually been run once
Docker is installed.

## Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin) installed and running

## Usage

```bash
docker compose up --build
```

This starts:

- `postgres` (PostgreSQL 16) on `5432`
- `redis` (Redis 7) on `6379`
- `backend` (FastAPI) on `8000`, wired to `postgres` and `redis`
- `frontend` (Next.js) on `3000`, wired to `backend`

All credentials in `docker-compose.yml` are local-development defaults
(`ai_receptionist` / `ai_receptionist`), overridable via a `.env` file at the
repo root (see `.env.example`) — never commit real values.

## Before relying on this in CI or production

1. Actually run `docker compose up --build` once Docker is available and fix
   anything that surfaces — it has not been executed yet.
2. Replace the default Postgres credentials with secrets management before
   any non-local use.
