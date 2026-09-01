#!/usr/bin/env bash
# Runs every verification command used in Phase 1: backend tests/lint/type-check,
# frontend lint/type-check/build, widget lint/type-check/build.
# Safe to re-run any time; makes no destructive changes.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "== Backend: pytest =="
(cd "$REPO_ROOT/backend" && .venv/bin/python -m pytest -q)

echo "== Backend: ruff =="
(cd "$REPO_ROOT/backend" && .venv/bin/python -m ruff check app tests)

echo "== Backend: mypy =="
(cd "$REPO_ROOT/backend" && .venv/bin/python -m mypy app)

echo "== Frontend: eslint =="
(cd "$REPO_ROOT/frontend" && npx eslint .)

echo "== Frontend: tsc =="
(cd "$REPO_ROOT/frontend" && npx tsc --noEmit)

echo "== Frontend: build =="
(cd "$REPO_ROOT/frontend" && npm run build)

echo "== Widget: eslint =="
(cd "$REPO_ROOT/widget" && npx eslint .)

echo "== Widget: tsc =="
(cd "$REPO_ROOT/widget" && npx tsc --noEmit)

echo "== Widget: build =="
(cd "$REPO_ROOT/widget" && npm run build)

echo "All checks passed."
