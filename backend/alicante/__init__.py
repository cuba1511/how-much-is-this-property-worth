"""Alicante MVP — fully isolated package.

Everything related to the Alicante MVP (local SQLite snapshot, real
transactions layer, dedicated `/api/valuation/alicante` endpoint) lives
in this package. Production `/api/valuation` and friends never import
from here — they continue to use the Bright Data scraper.

Public surface
--------------
- `router`           — FastAPI APIRouter wired in `main.py` via
                       `app.include_router(...)`.
- `storage.ensure_schema(conn)` — invoked automatically by `db.init_db()`
                       through the schema hook registered in `storage.py`.

ETL
---
`scripts/load_alicante.py` writes the SQLite snapshot via
`alicante.storage.bulk_upsert_*`. Run with `make load-alicante`.
"""
from __future__ import annotations

# Importing `storage` here triggers the `db.register_schema_hook` call, so
# the Alicante tables get created on the next `db.init_db()` without any
# explicit wiring needed from `main.py`.
from alicante import storage  # noqa: F401  (side-effect import)
from alicante.routes import router

__all__ = ["router", "storage"]
