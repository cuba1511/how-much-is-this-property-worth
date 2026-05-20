"""SQLite persistence for the Alicante MVP dataset.

Self-contained: owns its schema and all the queries that touch the
`alicante_listings` / `alicante_transactions` tables. Nothing in the rest
of the backend (production `db.py`, `valuation/`, `scraping/`) should
import this module — only the `alicante` package and the loader script
`scripts/load_alicante.py` do.

Schema is registered with the production DB via `db.register_schema_hook`
when this module is first imported, so calling `db.init_db()` continues to
be the single entry point for "make sure all tables exist".

Tables
------
- `alicante_listings`     — Snapshot of Idealista listings for Alicante
                            province (one row per gsraw_id). Loaded from
                            `Listing_Semanal` sheet.
- `alicante_transactions` — Aggregated closing KPIs per (boundary, period,
                            indicator, segment). NOT per-transaction rows.
                            Loaded from `Indicadores_Transacciones_Reales`.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Any, Optional

import db

logger = logging.getLogger(__name__)


SCHEMA_STATEMENTS: tuple[str, ...] = (
    # Snapshot of Idealista listings for Alicante province. Replaces the
    # Bright Data scraper when the geocoded municipio falls in coverage.
    """
    CREATE TABLE IF NOT EXISTS alicante_listings (
        gsraw_id              TEXT PRIMARY KEY,
        origin_id             TEXT,
        source_name           TEXT,
        operation_type_name   TEXT,
        usage_name            TEXT,
        property_type_name    TEXT,
        build_status_name     TEXT,
        conservation_name     TEXT,
        local_price           INTEGER,
        area                  INTEGER,
        n_rooms               INTEGER,
        n_baths               INTEGER,
        n_floor               TEXT,
        lat                   REAL,
        lon                   REAL,
        full_address          TEXT,
        is_exact_address      INTEGER,
        admin2                TEXT,
        admin3                TEXT,
        admin4                TEXT,
        admin5                TEXT,
        admin6                TEXT,
        boundary_id           INTEGER,
        has_storage           INTEGER,
        has_garage            INTEGER,
        has_pool              INTEGER,
        has_air_conditioner   INTEGER,
        has_elevator          INTEGER,
        has_terrace           INTEGER,
        has_common_zones      INTEGER,
        is_exterior           INTEGER,
        energy_cert_name      TEXT,
        year_of_construction  INTEGER,
        first_appearance      TEXT,
        last_appearance       TEXT,
        delivery_week         TEXT,
        title                 TEXT,
        first_image_url       TEXT,
        ine_code              TEXT,
        snapshot_at           TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_alicante_listings_geo
        ON alicante_listings(lat, lon)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_alicante_listings_admin3
        ON alicante_listings(admin3, property_type_name, operation_type_name)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_alicante_listings_rooms_area
        ON alicante_listings(n_rooms, n_baths, area)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_alicante_listings_boundary
        ON alicante_listings(boundary_id)
    """,
    # Closing-price KPIs (Indicadores_Transacciones_Reales). Aggregated per
    # (boundary, period, indicator, segment) — NOT per individual transaction.
    # transactions.py uses indicator 102 (avg €/m²), 104 (avg €), 108 (avg margin), …
    """
    CREATE TABLE IF NOT EXISTS alicante_transactions (
        table_id            TEXT PRIMARY KEY,
        boundary_type       INTEGER,
        boundary_id         INTEGER,
        operation_type_id   INTEGER,
        period_id           TEXT,
        indicator_id        INTEGER,
        segment_id          INTEGER,
        calculated_value    REAL,
        estimated_value     REAL,
        execution_datetime  TEXT,
        snapshot_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_alicante_transactions_lookup
        ON alicante_transactions(boundary_id, indicator_id, period_id)
    """,
)


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create Alicante tables/indexes if missing. Idempotent.

    Called automatically by `db.init_db()` via the schema-hook registered at
    module import time, so the rest of the app never needs to call it.
    """
    for statement in SCHEMA_STATEMENTS:
        conn.execute(statement)


# Register the schema with production `db.init_db()` so it runs alongside
# the production tables. Doing it at import time means anything that imports
# the `alicante` package will trigger schema creation on the next init_db().
db.register_schema_hook(ensure_schema)


# ────────────────────────────────────────────────────────────────────────
# Read helpers
# ────────────────────────────────────────────────────────────────────────


def listings_count() -> int:
    """Quick sanity check for routing — 0 means dataset not loaded yet."""
    with db.connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM alicante_listings").fetchone()
    return int(row["n"] or 0)


def transactions_count() -> int:
    with db.connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM alicante_transactions").fetchone()
    return int(row["n"] or 0)


def query_listings_raw(
    *,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    area_min: Optional[int],
    area_max: Optional[int],
    rooms_min: Optional[int],
    rooms_max: Optional[int],
    baths_min: Optional[int],
    baths_max: Optional[int],
    operation_type: str = "Venta",
    usage: str = "Residencial",
    property_type: Optional[str] = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Bounding-box + filter query over the Alicante listings snapshot.

    Returns raw row dicts. The caller is responsible for any further
    refinement (haversine distance, ranking, mapping to `Listing`).
    """
    clauses: list[str] = [
        "lat IS NOT NULL AND lon IS NOT NULL",
        "lat BETWEEN ? AND ?",
        "lon BETWEEN ? AND ?",
        "operation_type_name = ?",
        "usage_name = ?",
        "local_price IS NOT NULL AND local_price > 0",
        "area IS NOT NULL AND area > 0",
    ]
    params: list[Any] = [lat_min, lat_max, lon_min, lon_max, operation_type, usage]

    if property_type:
        clauses.append("property_type_name = ?")
        params.append(property_type)
    if area_min is not None:
        clauses.append("area >= ?")
        params.append(area_min)
    if area_max is not None:
        clauses.append("area <= ?")
        params.append(area_max)
    if rooms_min is not None:
        clauses.append("(n_rooms IS NULL OR n_rooms >= ?)")
        params.append(rooms_min)
    if rooms_max is not None:
        clauses.append("(n_rooms IS NULL OR n_rooms <= ?)")
        params.append(rooms_max)
    if baths_min is not None:
        clauses.append("(n_baths IS NULL OR n_baths >= ?)")
        params.append(baths_min)
    if baths_max is not None:
        clauses.append("(n_baths IS NULL OR n_baths <= ?)")
        params.append(baths_max)

    sql = f"""
        SELECT *
        FROM alicante_listings
        WHERE {' AND '.join(clauses)}
        LIMIT ?
    """
    params.append(max(1, min(limit, 2000)))

    with db.connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def query_transactions_latest(
    *,
    boundary_id: int,
    indicator_ids: list[int],
    operation_type_id: int = 10,
    segment_id: int = 0,
) -> dict[int, dict[str, Any]]:
    """Latest period KPI per indicator for a given boundary, op-type, segment.

    Defaults to `operation_type_id=10` (residential sales) and `segment_id=0`
    (no further breakdown) — the slice that matches "buying an apartment in
    Alicante". The dataset has 6 distinct op-types per boundary and selecting
    the wrong one returns rentals/garages/land instead of residential sales.

    Returns `{indicator_id: row_dict}`. Missing indicators are omitted —
    callers must handle the absence.
    """
    if not indicator_ids:
        return {}

    placeholders = ",".join("?" for _ in indicator_ids)
    sql = f"""
        SELECT *
        FROM alicante_transactions
        WHERE boundary_id = ?
          AND operation_type_id = ?
          AND segment_id = ?
          AND indicator_id IN ({placeholders})
          AND calculated_value IS NOT NULL
        ORDER BY period_id DESC
    """
    params = [boundary_id, operation_type_id, segment_id, *indicator_ids]

    with db.connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    latest: dict[int, dict[str, Any]] = {}
    for row in rows:
        ind = int(row["indicator_id"])
        if ind not in latest:
            latest[ind] = dict(row)
    return latest


def municipio_asking_aggregates(
    *,
    admin3: str = "Alicante/Alacant",
    property_type: str = "Pisos",
    operation_type: str = "Venta",
) -> dict[str, Optional[float]]:
    """Whole-municipio asking-price aggregates from the listings snapshot.

    Used by `transactions.build_alicante_transactions` to compare against
    closing KPIs at the same scope (avoids the "premium-neighborhood asking
    vs municipio-wide closing" apples-to-oranges gap).
    """
    sql = """
        SELECT
            COUNT(*)                                            AS n,
            AVG(local_price)                                    AS avg_price,
            AVG(CAST(local_price AS REAL) / NULLIF(area, 0))    AS avg_ppm2
        FROM alicante_listings
        WHERE admin3 = ?
          AND property_type_name = ?
          AND operation_type_name = ?
          AND local_price > 0
          AND area > 0
    """
    with db.connect() as conn:
        row = conn.execute(sql, (admin3, property_type, operation_type)).fetchone()
    if not row:
        return {"n": 0, "avg_price": None, "avg_ppm2": None}
    return {
        "n": int(row["n"] or 0),
        "avg_price": float(row["avg_price"]) if row["avg_price"] is not None else None,
        "avg_ppm2": float(row["avg_ppm2"]) if row["avg_ppm2"] is not None else None,
    }


# ────────────────────────────────────────────────────────────────────────
# Write helpers — used by scripts/load_alicante.py
# ────────────────────────────────────────────────────────────────────────


_LISTING_COLUMNS = (
    "gsraw_id", "origin_id", "source_name", "operation_type_name",
    "usage_name", "property_type_name", "build_status_name",
    "conservation_name", "local_price", "area", "n_rooms", "n_baths",
    "n_floor", "lat", "lon", "full_address", "is_exact_address",
    "admin2", "admin3", "admin4", "admin5", "admin6", "boundary_id",
    "has_storage", "has_garage", "has_pool", "has_air_conditioner",
    "has_elevator", "has_terrace", "has_common_zones", "is_exterior",
    "energy_cert_name", "year_of_construction", "first_appearance",
    "last_appearance", "delivery_week", "title", "first_image_url",
    "ine_code",
)

_TRANSACTION_COLUMNS = (
    "table_id", "boundary_type", "boundary_id", "operation_type_id",
    "period_id", "indicator_id", "segment_id", "calculated_value",
    "estimated_value", "execution_datetime",
)


def bulk_upsert_listings(rows: list[dict[str, Any]]) -> int:
    """Insert-or-replace listings keyed by `gsraw_id`. Used by the ETL script."""
    if not rows:
        return 0

    placeholders = ", ".join(["?"] * len(_LISTING_COLUMNS))
    sql = (
        f"INSERT OR REPLACE INTO alicante_listings ({', '.join(_LISTING_COLUMNS)}) "
        f"VALUES ({placeholders})"
    )
    payload = [tuple(row.get(col) for col in _LISTING_COLUMNS) for row in rows]

    with db.connect() as conn:
        conn.executemany(sql, payload)
        conn.commit()
    return len(payload)


def bulk_upsert_transactions(rows: list[dict[str, Any]]) -> int:
    """Insert-or-replace transaction-indicator rows keyed by `table_id`."""
    if not rows:
        return 0

    placeholders = ", ".join(["?"] * len(_TRANSACTION_COLUMNS))
    sql = (
        f"INSERT OR REPLACE INTO alicante_transactions ({', '.join(_TRANSACTION_COLUMNS)}) "
        f"VALUES ({placeholders})"
    )
    payload = [tuple(row.get(col) for col in _TRANSACTION_COLUMNS) for row in rows]

    with db.connect() as conn:
        conn.executemany(sql, payload)
        conn.commit()
    return len(payload)


__all__ = [
    "ensure_schema",
    "listings_count",
    "transactions_count",
    "query_listings_raw",
    "query_transactions_latest",
    "municipio_asking_aggregates",
    "bulk_upsert_listings",
    "bulk_upsert_transactions",
]
