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

# ── Dev servers ───────────────────────────────────────────────────────────────

.PHONY: backend
backend:
	@[ -f backend/.env ] || (echo "⚠  backend/.env not found — run: make install" && exit 1)
	cd backend && .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8001 --reload

.PHONY: frontend
frontend: $(FRONT)/node_modules
	cd $(FRONT) && npm run dev

# Runs API + Vite dev server side-by-side. Ctrl+C cleanly tears both down.
.PHONY: dev
dev: $(VENV) $(FRONT)/node_modules
	@[ -f backend/.env ] || (echo "⚠  backend/.env not found — run: make install" && exit 1)
	@echo ""
	@echo "  ▶  API      → http://localhost:8001"
	@echo "  ▶  Frontend → http://localhost:5173  (proxies API calls to :8001)"
	@echo ""
	@trap 'kill 0' SIGINT SIGTERM EXIT; \
	(cd backend && .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8001 --reload) & \
	(cd $(FRONT) && npm run dev) & \
	wait

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
	rm -rf $(VENV) $(FRONT)/node_modules
	@echo "✓ All deps removed. Re-run make install."

# ── Help ──────────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@echo ""
	@echo "  Setup"
	@echo "    make install     Install Python + Node deps and Playwright Chromium"
	@echo "    make db          Create the SQLite file (backend/data/prophero.db)"
	@echo ""
	@echo "  Run"
	@echo "    make dev         API + frontend side-by-side (recommended)"
	@echo "    make backend     Only the FastAPI server → :8001"
	@echo "    make frontend    Only the Vite dev server → :5173"
	@echo ""
	@echo "  Cleanup"
	@echo "    make clean       Remove caches, build outputs, and the local DB"
	@echo "    make clean-deps  Also remove node_modules and the Python venv"
	@echo ""
