#!/usr/bin/env bash
# Runs the FastAPI backend locally (non-Docker path) with auto-reload.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT/backend"

if [ ! -d .venv ]; then
  echo "Virtual environment not found. Run: python3 -m venv .venv && .venv/bin/python -m ensurepip --upgrade (or bootstrap pip via get-pip.py if ensurepip is unavailable), then .venv/bin/python -m pip install -r requirements-dev.txt" >&2
  exit 1
fi

exec .venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
