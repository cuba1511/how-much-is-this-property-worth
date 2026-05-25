"""One-shot CSV → SQLite preprocessor for the market price series.

Reads `backend/data/sale_price_sqm_p50_smooth_series_*.csv` (TF Labs export,
~2M rows, ~250 MB on disk) and produces a compact SQLite file at
`backend/data/market_price_series.db` that the FastAPI server can query in
constant time.

Schema (normalized to keep the file small — town metadata is repeated 254
times across periods in the CSV, so we factor it out):

    CREATE TABLE market_towns (
        town_id        TEXT PRIMARY KEY,  -- Airtable record id (CSV `town_id`)
        ine_code       TEXT NOT NULL,     -- 5-digit INE code (CSV `geo_key`)
        town_name      TEXT NOT NULL,     -- Spanish name (CSV `entity_label`)
        town_name_norm TEXT NOT NULL,     -- lowercased + accent-stripped
        province_id    TEXT,
        community_id   TEXT
    );
    CREATE INDEX idx_market_ine_code  ON market_towns (ine_code);
    CREATE INDEX idx_market_town_name ON market_towns (town_name_norm);

    CREATE TABLE market_price_series (
        town_id TEXT NOT NULL REFERENCES market_towns(town_id),
        period  TEXT NOT NULL,  -- "YYYY-MM"
        value   REAL NOT NULL,  -- median sale price €/m² (smoothed)
        PRIMARY KEY (town_id, period)
    );

Filtering rules:
- Only `aggregation_level = TOWN` rows are kept (the export only ships TOWN
  rows today, but we still check defensively).
- Rows with `value = NULL` are dropped.
- The projected `period = 2029-01` row is dropped — it's a forecast, not an
  observation. Adjust ``PROJECTION_PERIODS`` if more forecast horizons land.

Re-run with ``make build-market-series`` (or ``python backend/scripts/build_market_price_series.py``).
The script is idempotent: it drops and recreates the table on every run.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path
from typing import Iterable, Iterator

logger = logging.getLogger("build_market_price_series")

# Repo root: this file lives at backend/scripts/, so go up twice.
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV = REPO_ROOT / "backend" / "data" / "sale_price_sqm_p50_smooth_series_2029_01_long.csv"
DEFAULT_DB = REPO_ROOT / "backend" / "data" / "market_price_series.db"

EXPECTED_METRIC = "SALE_PRICE_SQM_P50_SMOOTH"
EXPECTED_LEVEL = "TOWN"
# Projection periods that must not leak into "current market" lookups.
PROJECTION_PERIODS = {"2029-01"}


def _normalize_name(name: str) -> str:
    """Lowercase + strip accents, for forgiving municipality lookups.

    The CSV uses Spanish names with accents (e.g. ``Alegría-Dulantzi``);
    Nominatim sometimes returns the same name without diacritics, so we
    index a normalized column alongside the original one.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower().strip()


TownMeta = tuple  # (town_id, ine_code, town_name, town_name_norm, province_id, community_id)
SeriesRow = tuple  # (town_id, period, value)


def _iter_csv_rows(csv_path: Path) -> Iterator[tuple[TownMeta, SeriesRow]]:
    """Yield ``(town_meta, series_row)`` pairs ready for SQLite insertion.

    The town metadata is repeated on every CSV row; the build step
    deduplicates it into the ``market_towns`` table.
    """
    with csv_path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row.get("metric") != EXPECTED_METRIC:
                continue
            if row.get("aggregation_level") != EXPECTED_LEVEL:
                continue
            period = row.get("period") or ""
            if period in PROJECTION_PERIODS:
                continue
            raw_value = row.get("value")
            if raw_value is None or raw_value == "" or raw_value == "NULL":
                continue
            try:
                value = float(raw_value)
            except ValueError:
                continue
            town_id = (row.get("town_id") or "").strip()
            ine_code = (row.get("geo_key") or "").strip()
            town_name = (row.get("entity_label") or "").strip()
            if not town_id or not ine_code or not town_name:
                continue
            town_meta = (
                town_id,
                ine_code,
                town_name,
                _normalize_name(town_name),
                (row.get("province_id") or "").strip() or None,
                (row.get("community_id") or "").strip() or None,
            )
            yield town_meta, (town_id, period, value)


def _batched(rows: Iterable[tuple], size: int) -> Iterator[list[tuple]]:
    batch: list[tuple] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def build(csv_path: Path, db_path: Path, batch_size: int = 50_000) -> dict[str, int]:
    """Build the SQLite database from the CSV. Returns a stats dict."""
    if not csv_path.exists():
        raise FileNotFoundError(
            f"CSV not found at {csv_path}. Drop the TF Labs export there "
            "before running `make build-market-series`."
        )

    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = db_path.with_suffix(db_path.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    started = time.monotonic()
    inserted = 0
    seen_towns: dict[str, TownMeta] = {}

    conn = sqlite3.connect(tmp_path)
    try:
        conn.execute("PRAGMA journal_mode = OFF")
        conn.execute("PRAGMA synchronous = OFF")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.executescript(
            """
            DROP TABLE IF EXISTS market_price_series;
            DROP TABLE IF EXISTS market_towns;
            CREATE TABLE market_towns (
                town_id        TEXT PRIMARY KEY,
                ine_code       TEXT NOT NULL,
                town_name      TEXT NOT NULL,
                town_name_norm TEXT NOT NULL,
                province_id    TEXT,
                community_id   TEXT
            );
            CREATE TABLE market_price_series (
                town_id TEXT NOT NULL REFERENCES market_towns(town_id),
                period  TEXT NOT NULL,
                value   REAL NOT NULL,
                PRIMARY KEY (town_id, period)
            ) WITHOUT ROWID;
            """
        )

        insert_series_sql = (
            "INSERT OR REPLACE INTO market_price_series (town_id, period, value) VALUES (?, ?, ?)"
        )

        def _series_only() -> Iterator[SeriesRow]:
            nonlocal inserted
            for town_meta, series_row in _iter_csv_rows(csv_path):
                town_id = town_meta[0]
                if town_id not in seen_towns:
                    seen_towns[town_id] = town_meta
                inserted += 1
                if inserted % (batch_size * 4) == 0:
                    logger.info("…processed %s rows", f"{inserted:,}")
                yield series_row

        for batch in _batched(_series_only(), batch_size):
            conn.executemany(insert_series_sql, batch)

        conn.executemany(
            "INSERT INTO market_towns "
            "(town_id, ine_code, town_name, town_name_norm, province_id, community_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            seen_towns.values(),
        )

        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_market_ine_code  ON market_towns (ine_code);
            CREATE INDEX IF NOT EXISTS idx_market_town_name ON market_towns (town_name_norm);
            """
        )
        conn.commit()
        # VACUUM compacts the file after the big bulk insert. Worth the
        # extra ~1 s because the artifact is read-only at runtime.
        conn.execute("VACUUM")

        towns = conn.execute("SELECT COUNT(*) FROM market_towns").fetchone()[0]
        first_period, last_period = conn.execute(
            "SELECT MIN(period), MAX(period) FROM market_price_series"
        ).fetchone()
    finally:
        conn.close()

    # Atomic swap so a partial build never overwrites a working DB.
    db_path.unlink(missing_ok=True)
    os.replace(tmp_path, db_path)

    elapsed = time.monotonic() - started
    return {
        "rows_inserted": inserted,
        "towns": towns,
        "first_period": first_period,
        "last_period": last_period,
        "elapsed_seconds": round(elapsed, 2),
        "db_path": str(db_path),
        "db_size_mb": round(db_path.stat().st_size / (1024 * 1024), 1),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV,
        help=f"Source CSV (default: {DEFAULT_CSV.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help=f"Destination SQLite (default: {DEFAULT_DB.relative_to(REPO_ROOT)})",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress progress logs")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    try:
        stats = build(args.csv, args.db)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 2

    logger.info(
        "Built %s rows / %s towns covering %s → %s in %.2fs (%.1f MB) at %s",
        f"{stats['rows_inserted']:,}",
        f"{stats['towns']:,}",
        stats["first_period"],
        stats["last_period"],
        stats["elapsed_seconds"],
        stats["db_size_mb"],
        stats["db_path"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
