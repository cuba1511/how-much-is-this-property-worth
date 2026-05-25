# Market price series (municipal €/m²)

## Purpose

Real-data layer for the **zone appreciation** number shown in the coach
investor report. Replaces the previous "estimated value − total paid"
heuristic for capital gain with something defensible:

> "Cuánto ha apreciado la mediana €/m² del municipio entre la firma
>  (`Real settlement date`) y el último mes disponible en la serie."

## Source

| Field         | Value                                                            |
| ------------- | ---------------------------------------------------------------- |
| Provider      | TF Labs (`SALE_PRICE_SQM_P50_SMOOTH`)                            |
| Granularity   | Municipality (`aggregation_level = TOWN`)                        |
| Frequency     | Monthly                                                          |
| Coverage      | 2005-01 → 2026-01 (≈ 8 000 Spanish municipalities)               |
| Raw file      | `backend/data/sale_price_sqm_p50_smooth_series_2029_01_long.csv` |
| Built artifact| `backend/data/market_price_series.db` (SQLite, ~54 MB)           |

The CSV ships out-of-band (gitignored). Drop it at the path above before
running the build step.

## Build pipeline

```bash
make build-market-series
# ≈ 7 s, 1.4M rows / 8 017 towns / 2005-01 → 2026-01
```

The script lives at [`backend/scripts/build_market_price_series.py`](../backend/scripts/build_market_price_series.py)
and is idempotent — it overwrites the SQLite file atomically. It drops:

- non-`TOWN` rows (defensive, the export only ships `TOWN`)
- rows with `value = NULL`
- the projected `2029-01` row (forecast — must not leak into "latest market" lookups)

## Schema

```sql
CREATE TABLE market_towns (
    town_id        TEXT PRIMARY KEY,  -- Airtable record id (CSV `town_id`)
    ine_code       TEXT NOT NULL,     -- 5-digit INE municipal code
    town_name      TEXT NOT NULL,     -- Spanish name (CSV `entity_label`)
    town_name_norm TEXT NOT NULL,     -- lowercased + accent-stripped
    province_id    TEXT,
    community_id   TEXT
);
CREATE TABLE market_price_series (
    town_id TEXT NOT NULL REFERENCES market_towns(town_id),
    period  TEXT NOT NULL,  -- "YYYY-MM"
    value   REAL NOT NULL,  -- median sale price €/m² (smoothed)
    PRIMARY KEY (town_id, period)
) WITHOUT ROWID;
```

Town metadata is repeated 254 times in the CSV (once per period) so we
factor it out — that's why the SQLite is ~5× smaller than the raw CSV.

## Runtime API

`backend/market/price_series.py` exposes:

- `PriceSeriesStore(db_path)` — opens a read-only (`mode=ro`) SQLite
  connection with `check_same_thread=False`. Safe to share across FastAPI
  worker threads.
- `get_default_store()` — lazy module-level singleton. Returns `None` and
  logs once if the SQLite is missing — the API stays up and the
  appreciation block is simply omitted from the response.
- `compute_appreciation(store, town, settlement_date) → MarketAppreciation`
  — wraps the period math (months elapsed, annualized %, baseline
  fallback when settlement is before 2005-01).

### Town resolution chain

The store tries identifiers in priority order:

1. **Airtable record id** — `town_record_id` extracted from the
   `Transactions` table (lookup field from Properties). Highest signal,
   matches the CSV `town_id` directly.
2. **INE code** — for callers that already know the 5-digit code.
3. **Municipality name** — accent-stripped, lowercased match against
   `town_name_norm`. Province id narrows the search when present.

The resolved row is returned with a `resolution_strategy` tag
(`"airtable_town_id" | "ine_code" | "name_match"`) so the frontend can
display the source if needed.

## API contract

`POST /api/coach/transactions/{record_id}/valuation` now returns an
optional `market_appreciation` block inside `valuation`:

```json
{
  "market_appreciation": {
    "town_id": "recfxR1bXFsAcGrn7",
    "town_name": "Madrid",
    "ine_code": "28079",
    "settlement_date": "2022-06-15",
    "from_period": "2022-06",
    "from_eur_per_m2": 3360.81,
    "to_period": "2026-01",
    "to_eur_per_m2": 5621.27,
    "pct_change": 0.6726,
    "annualized_pct_change": 0.1544,
    "months_elapsed": 43,
    "sample_quality": "exact",
    "resolution_strategy": "ine_code"
  }
}
```

`sample_quality` is `"exact"` when the exact `YYYY-MM` was present in the
series, `"nearest_available"` when the lookup fell back to an earlier
period (e.g. settlement before 2005-01).

The block is `null` (omitted from the response) whenever:

- the SQLite artifact is missing (`get_default_store()` returned `None`),
- the transaction has no `Real settlement date`,
- the town could not be resolved via any of the three strategies.

The coach report degrades gracefully in any of these cases — the
"Apreciación de zona" card simply doesn't render.

## Deployment notes

- `*.db` is gitignored. The SQLite artifact must be produced on the
  target host by running `make build-market-series` *after* the CSV has
  been uploaded (or rsync the prebuilt SQLite directly).
- `make clean` deletes the entire `backend/data/` directory. You'll need
  to re-place the CSV and rerun `make build-market-series` afterwards.
- The CSV doesn't fit a git repo (250 MB). Long-term we can move it
  behind a signed S3 URL fetched at build time; the build script already
  accepts `--csv` so wiring that up is one flag away.

## Future work

- Add a `province` aggregation level so partial address matches still
  produce *some* signal.
- Surface `sample_quality = "nearest_available"` as a UI badge so the
  coach knows when the baseline was approximated.
- Add a CLI flag to ship a Parquet artifact alongside the SQLite for
  notebook-based analytics.
