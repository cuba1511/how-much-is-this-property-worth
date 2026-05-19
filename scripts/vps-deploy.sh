#!/usr/bin/env bash
# Build frontend + restart Docker stack.
# Requires env vars in the shell (GitHub Actions secrets via SSH, or local export).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export SITE_ADDRESS="${SITE_ADDRESS:-:80}"
: "${BRIGHT_DATA_CDP:?BRIGHT_DATA_CDP is not set}"

if [[ ! -d frontend/node_modules ]]; then
  echo "→ npm ci (frontend)"
  (cd frontend && npm ci)
fi

echo "→ npm run build (frontend, same-origin API)"
(cd frontend && npm run build)

echo "→ docker compose up -d --build"
docker compose up -d --build

echo ""
docker compose ps
echo ""
echo "Health: curl -sS http://127.0.0.1/health"
echo "Logs:   docker compose logs -f api"
