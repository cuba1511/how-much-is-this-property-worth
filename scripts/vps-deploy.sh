#!/usr/bin/env bash
# Build frontend + (re)start Docker stack. Run on the VPS after git pull.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f deploy/.env ]]; then
  echo "Missing deploy/.env — run: cp deploy/env.example deploy/.env && edit secrets"
  exit 1
fi

if [[ ! -d frontend/node_modules ]]; then
  echo "→ npm ci (frontend)"
  (cd frontend && npm ci)
fi

echo "→ npm run build (frontend, same-origin API)"
(cd frontend && npm run build)

echo "→ docker compose up -d --build"
docker compose --env-file deploy/.env up -d --build

echo ""
docker compose ps
echo ""
echo "Health: curl -sS http://127.0.0.1/health  (or https://YOUR_DOMAIN/health)"
echo "Logs:   docker compose logs -f api"
