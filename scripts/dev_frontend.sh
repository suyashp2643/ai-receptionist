#!/usr/bin/env bash
# Runs the Next.js frontend locally (non-Docker path).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT/frontend"

exec npm run dev
