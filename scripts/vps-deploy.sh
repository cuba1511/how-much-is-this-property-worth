#!/usr/bin/env bash
# Build frontend + restart Docker stack.
# Requires env vars in the shell (GitHub Actions secrets via SSH, or local export).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export SITE_ADDRESS="${SITE_ADDRESS:-:80}"
: "${BRIGHT_DATA_CDP:?BRIGHT_DATA_CDP is not set}"

# Always run `npm ci` when the lockfile is newer than node_modules — otherwise
# new dependencies added in a commit (e.g. react-router-dom) never get
# installed on the server and `npm run build` fails with TS2307. The previous
# heuristic ("install only when node_modules is missing") meant the first
# successful deploy permanently froze the dep tree on disk.
if [[ ! -d frontend/node_modules ]] \
   || [[ frontend/package-lock.json -nt frontend/node_modules/.package-lock.json ]] \
   || [[ frontend/package.json -nt frontend/node_modules/.package-lock.json ]]; then
  echo "→ npm ci (frontend) — lockfile or package.json changed"
  (cd frontend && npm ci)
else
  echo "→ npm ci skipped (node_modules up to date)"
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
