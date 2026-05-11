VENV   := backend/.venv
PYTHON := $(VENV)/bin/python
PIP    := $(VENV)/bin/pip

# ── Setup ─────────────────────────────────────────────────────────────────────

.PHONY: install
install: $(VENV)
	$(PIP) install -r backend/requirements.txt
	$(PYTHON) -m playwright install chromium
	@echo ""
	@echo "✓ Done. Copy env file: cp .env.example backend/.env"

$(VENV):
	python3 -m venv $(VENV)

# ── Dev server (front + back in one process) ──────────────────────────────────

.PHONY: dev
dev:
	@[ -f backend/.env ] || (echo "⚠  backend/.env not found — run: cp .env.example backend/.env" && exit 1)
	cd backend && .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8001 --reload

# ── Help ──────────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@echo ""
	@echo "  make install   Install Python deps + Playwright Chromium browser"
	@echo "  make dev       Start API + frontend → http://localhost:8001"
	@echo ""
