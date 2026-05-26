VENV   := backend/.venv
PYTHON := $(VENV)/bin/python
PIP    := $(VENV)/bin/pip
FRONT  := frontend

# ── Setup ─────────────────────────────────────────────────────────────────────

.PHONY: install
install: $(VENV) $(FRONT)/node_modules
	$(PIP) install -q -r backend/requirements.txt
	$(PYTHON) -m playwright install chromium
	@[ -f backend/.env ] || (cp .env.example backend/.env && echo "✓ Created backend/.env from .env.example — edit it before running make dev")
	@if [ -f .env ] && [ ! -s backend/.env ] 2>/dev/null; then \
		echo "⚠  Tienes .env en la raíz pero backend/.env está vacío — copia las variables a backend/.env"; \
	elif [ -f .env ]; then \
		echo "ℹ  .env en la raíz detectado — el backend solo lee backend/.env (ver docs/structure.md)"; \
	fi
	@echo ""
	@echo "✓ Install complete. Next: make db && make dev"

$(VENV):
	python3 -m venv $(VENV)

$(FRONT)/node_modules: $(FRONT)/package.json
	cd $(FRONT) && npm install
	@touch $@

# ── DB ────────────────────────────────────────────────────────────────────────

.PHONY: db
db: $(VENV)
	@cd backend && ../$(PYTHON) -c "import db; print('SQLite ready at', db.init_db())"

# Rebuilds backend/data/market_price_series.db from the TF Labs CSV export.
# The CSV ships out-of-band (gitignored) — see docs/market-price-series.md.
.PHONY: build-market-series
build-market-series: $(VENV)
	$(PYTHON) backend/scripts/build_market_price_series.py

# ── Dev servers ───────────────────────────────────────────────────────────────

.PHONY: backend
backend:
	@[ -f backend/.env ] || (echo "⚠  backend/.env not found — run: make install" && exit 1)
	cd backend && .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8001 --reload

.PHONY: frontend
frontend: $(FRONT)/node_modules
	cd $(FRONT) && npm run dev

# Runs API + Vite dev server side-by-side. Ctrl+C cleanly tears both down,
# including any uvicorn worker that's stuck waiting on an httpx response —
# we send SIGINT first (lets uvicorn shutdown gracefully) and a SIGKILL
# follow-up after 3s so a hung HTTP call can never keep :8001 captive.
.PHONY: dev
dev: $(VENV) $(FRONT)/node_modules
	@[ -f backend/.env ] || (echo "⚠  backend/.env not found — run: make install" && exit 1)
	@echo ""
	@echo "  ▶  API      → http://localhost:8001"
	@echo "  ▶  Frontend → http://localhost:5173  (proxies API calls to :8001)"
	@echo ""
	@trap 'kill -INT 0 2>/dev/null; sleep 3; kill -KILL 0 2>/dev/null' SIGINT SIGTERM EXIT; \
	(cd backend && .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8001 --reload) & \
	(cd $(FRONT) && npm run dev) & \
	wait

# Force-kill anything holding the API or Vite port. Handy when `make dev`
# was Ctrl+C'd while a request to Airtable / Idealista was in flight.
.PHONY: dev-stop
dev-stop:
	-@lsof -nP -iTCP:8001 -sTCP:LISTEN -t 2>/dev/null | xargs -r kill -KILL
	-@lsof -nP -iTCP:5173 -sTCP:LISTEN -t 2>/dev/null | xargs -r kill -KILL
	-@lsof -nP -iTCP:5174 -sTCP:LISTEN -t 2>/dev/null | xargs -r kill -KILL
	@echo "✓ Ports 8001, 5173 and 5174 free."

# ── VPS (Docker + Caddy) ─────────────────────────────────────────────────────

.PHONY: vps-build vps-up vps-down vps-logs
vps-build: $(FRONT)/node_modules
	@echo "→ Building frontend for same-origin /api (VITE_API_URL empty)"
	cd $(FRONT) && npm run build

vps-up: vps-build
	@test -n "$$SITE_ADDRESS" || (echo "⚠  Export SITE_ADDRESS, ACME_EMAIL, BRIGHT_DATA_CDP (see deploy/env.example)" && exit 1)
	docker compose up -d --build
	@echo ""
	@echo "  ▶  Stack up. Test: curl http://127.0.0.1/health"
	@echo "  ▶  Logs: make vps-logs"

vps-down:
	docker compose down

vps-logs:
	docker compose logs -f

# ── Housekeeping ──────────────────────────────────────────────────────────────

.PHONY: clean
clean:
	@echo "removing caches, build outputs, and the local SQLite db…"
	find backend -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf backend/data
	rm -rf $(FRONT)/dist $(FRONT)/.vite tests/evaluation/.cache tests/evaluation/reports/*.md 2>/dev/null || true
	@echo "✓ Clean. Run make db to recreate SQLite."

.PHONY: clean-deps
clean-deps: clean
	rm -rf $(VENV) venv $(FRONT)/node_modules
	@echo "✓ All deps removed. Re-run make install."

# ── Help ──────────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@echo ""
	@echo "  Setup"
	@echo "    make install     Install Python + Node deps and Playwright Chromium"
	@echo "    make db          Create the SQLite file (backend/data/prophero.db)"
	@echo "    make build-market-series   Rebuild market_price_series.db from CSV"
	@echo ""
	@echo "  Run (local)"
	@echo "    make dev         API + frontend side-by-side (recommended)"
	@echo "    make backend     Only the FastAPI server → :8001"
	@echo "    make frontend    Only the Vite dev server → :5173"
	@echo "    make dev-stop    Free :8001 and :5173 (use if dev got stuck)"
	@echo ""
	@echo "  Deploy (VPS)"
	@echo "    make vps-up      Build UI + docker compose (needs deploy/.env)"
	@echo "    make vps-down    Stop containers"
	@echo "    make vps-logs    Follow api + caddy logs"
	@echo ""
	@echo "  Cleanup"
	@echo "    make clean       Remove caches, build outputs, and the local DB"
	@echo "    make clean-deps  Also remove node_modules and the Python venv"
	@echo ""
