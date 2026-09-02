#!/usr/bin/env bash
# Runs every verification command used across every phase so far: backend
# tests/lint/type-check (including the Phase 4 PostgreSQL multi-connection
# integration suite whenever DATABASE_URL is configured — see
# tests/integration/), frontend lint/type-check/vitest/build, widget
# lint/type-check/vitest/build/bundle (Phase 5).
# Safe to re-run any time; makes no destructive changes to shared data (the
# multi-connection suite creates and deletes only its own uniquely
# identifiable test tenants — see tests/integration/conftest.py).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "== Backend: pytest (full suite, includes multi-connection integration tests when DB is configured) =="
(cd "$REPO_ROOT/backend" && .venv/bin/python -m pytest -q)

echo "== Backend: pytest -m multiconn (explicit, for visibility — same tests already ran above) =="
(cd "$REPO_ROOT/backend" && .venv/bin/python -m pytest -m multiconn -v)

echo "== Backend: ruff =="
(cd "$REPO_ROOT/backend" && .venv/bin/python -m ruff check app tests)

echo "== Backend: mypy =="
(cd "$REPO_ROOT/backend" && .venv/bin/python -m mypy app)

echo "== Frontend: eslint =="
(cd "$REPO_ROOT/frontend" && npx eslint .)

echo "== Frontend: tsc =="
(cd "$REPO_ROOT/frontend" && npx tsc --noEmit)

echo "== Frontend: vitest =="
(cd "$REPO_ROOT/frontend" && npx vitest run)

echo "== Frontend: build =="
(cd "$REPO_ROOT/frontend" && npm run build)

echo "== Widget: eslint =="
(cd "$REPO_ROOT/widget" && npx eslint .)

echo "== Widget: tsc =="
(cd "$REPO_ROOT/widget" && npx tsc --noEmit)

echo "== Widget: vitest =="
(cd "$REPO_ROOT/widget" && npx vitest run)

echo "== Widget: build (type declarations) =="
(cd "$REPO_ROOT/widget" && npm run build)

echo "== Widget: bundle (production IIFE) =="
(cd "$REPO_ROOT/widget" && npm run bundle)

echo "All checks passed."
