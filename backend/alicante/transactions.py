"""Real market-transactions block for the Alicante MVP.

Drop-in replacement for `valuation.build_market_transactions_mock` when the
endpoint is the Alicante one. Produces the **same** `MarketTransactions`
shape so the frontend, PDF and email renderers don't need any changes.

Where the numbers come from
---------------------------
The dataset exposes two distinct layers:

- **Asking / offer side** — derived from `alicante_listings` (the Idealista
  listings snapshot). We compute average asking price + ppm² from the
  comparables window around the property.
- **Closing side** — derived from `alicante_transactions` (table
  `Indicadores_Transacciones_Reales`). These are aggregate KPIs per
  `(boundary, period, indicator)`, NOT per individual transaction. We pull
  the latest period for boundary 224 (Alicante/Alacant admin3) and segment 0
  (no breakdown). Relevant indicators (see `Descripción_indicadores`):
    - 101 — Average €/m² closing (median)
    - 102 — Average €/m² closing (mean)   ← preferred
    - 104 — Average price (€) closing (mean)
    - 108 — Gross margin (mean) — the canonical "negotiation factor"

When indicator 108 is unavailable we fall back to `(asking - closing) / asking`.

Per-transaction rows
--------------------
The dataset has no per-transaction records — only aggregates. We synthesize
the chart series and the per-row list from the nearest `alicante_listings`
asking prices, applying the boundary-level margin to derive an implied
closing price. The `source` field on each row is set to `alicante-derived`
(not "alicante-real") so callers know the closing component is modeled, not
observed at row level. The aggregate summary, however, IS the real closing
KPI from the dataset.
"""
from __future__ import annotations

import logging
import math
from statistics import mean
from typing import Optional

from models import (
    MarketTransaction,
    MarketTransactionChartPoint,
    MarketTransactions,
    MarketTransactionsSummary,
    MunicipioInfo,
)

from alicante import storage

logger = logging.getLogger(__name__)

# boundary_id for the Alicante/Alacant admin3 in this dataset.
ALICANTE_ADMIN3_BOUNDARY_ID = 224
# operation_type_id = 10 in `alicante_transactions` corresponds to residential
# sales for this dataset (avg sale ~276k€, ~2,530€/m² in 2025Q2). Other op
# types (20/30/40/50) cover rentals, garages, land, etc. — choosing the
# wrong code produces nonsense closing prices.
ALICANTE_RESIDENTIAL_OP_TYPE = 10
ALICANTE_ADMIN3_NAME = "Alicante/Alacant"

INDICATOR_CLOSING_PPM2_AVG = 102
INDICATOR_CLOSING_PPM2_MEDIAN = 101
INDICATOR_CLOSING_PRICE_AVG = 104
INDICATOR_CLOSING_PRICE_MEDIAN = 103

DEFAULT_TRANSACTION_COUNT = 6
MAX_CHART_SERIES_ROWS = 6

# Bounding box around the property — used ONLY for the per-row synthetic
# transactions (chart series). Aggregates use the full municipio scope so
# asking and closing stay comparable.
BBOX_HALF_DEG = 0.035  # ~3.9 km
ALICANTE_FALLBACK_LAT = 38.345
ALICANTE_FALLBACK_LON = -0.481


def _round_pct(value: Optional[float]) -> Optional[float]:
    return round(value, 1) if value is not None else None


def _mean_int(values: list[int]) -> Optional[int]:
    return int(mean(values)) if values else None


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _short_label(address: Optional[str], fallback_index: int) -> str:
    if not address:
        return f"Comp {fallback_index}"
    head = address.split(",")[0].strip()
    if len(head) > 18:
        return head[:15].rstrip() + "..."
    return head or f"Comp {fallback_index}"


def _fetch_closing_kpis() -> dict[int, dict]:
    return storage.query_transactions_latest(
        boundary_id=ALICANTE_ADMIN3_BOUNDARY_ID,
        operation_type_id=ALICANTE_RESIDENTIAL_OP_TYPE,
        indicator_ids=[
            INDICATOR_CLOSING_PPM2_AVG,
            INDICATOR_CLOSING_PPM2_MEDIAN,
            INDICATOR_CLOSING_PRICE_AVG,
            INDICATOR_CLOSING_PRICE_MEDIAN,
        ],
        segment_id=0,
    )


def _fetch_neighborhood_listings(municipio: MunicipioInfo) -> list[dict]:
    anchor_lat = municipio.lat if municipio.lat is not None else ALICANTE_FALLBACK_LAT
    anchor_lon = municipio.lon if municipio.lon is not None else ALICANTE_FALLBACK_LON
    rows = storage.query_listings_raw(
        lat_min=anchor_lat - BBOX_HALF_DEG,
        lat_max=anchor_lat + BBOX_HALF_DEG,
        lon_min=anchor_lon - BBOX_HALF_DEG,
        lon_max=anchor_lon + BBOX_HALF_DEG,
        area_min=None,
        area_max=None,
        rooms_min=None,
        rooms_max=None,
        baths_min=None,
        baths_max=None,
        property_type="Pisos",
        limit=400,
    )
    # Sort by distance to anchor, keep the closest 40.
    decorated: list[tuple[float, dict]] = []
    for row in rows:
        lat = row.get("lat")
        lon = row.get("lon")
        if lat is None or lon is None:
            continue
        distance = _haversine_m(anchor_lat, anchor_lon, float(lat), float(lon))
        decorated.append((distance, row))
    decorated.sort(key=lambda t: t[0])
    return [row | {"_distance_m": distance} for distance, row in decorated[:40]]


def _pick_period(*rows: Optional[dict]) -> Optional[str]:
    """Pick the latest non-empty period_id among the provided indicator rows."""
    periods = sorted({row["period_id"] for row in rows if row and row.get("period_id")})
    return periods[-1] if periods else None


def _derive_margin_pct(
    avg_asking_ppm2: Optional[float],
    avg_closing_ppm2: Optional[float],
) -> Optional[float]:
    """Margin = (asking - closing) / asking, in percentage points (6.3 → 6.3%).

    We intentionally derive the margin from the asking + closing aggregates
    rather than reading the dataset's `Gross margin` indicator. That indicator
    is reported in inconsistent units across periods in this snapshot, while
    `(asking − closing) / asking` is well-defined as long as both layers are
    computed at the same scope (municipio-wide here).
    """
    if avg_asking_ppm2 and avg_closing_ppm2 and avg_asking_ppm2 > 0:
        return _round_pct((1 - (avg_closing_ppm2 / avg_asking_ppm2)) * 100)
    return None


def _build_synthetic_transactions(
    listings: list[dict],
    *,
    margin_pct: Optional[float],
    period_id: Optional[str],
) -> list[MarketTransaction]:
    transactions: list[MarketTransaction] = []
    margin_ratio = (margin_pct / 100) if margin_pct is not None else None

    for index, row in enumerate(listings[:DEFAULT_TRANSACTION_COUNT], start=1):
        asking_price = int(row["local_price"]) if row.get("local_price") else None
        area = int(row["area"]) if row.get("area") else None
        asking_ppm2 = (
            int(asking_price / area)
            if asking_price and area and area > 0
            else None
        )

        closing_ppm2: Optional[int] = None
        closing_price: Optional[int] = None
        if margin_ratio is not None and asking_ppm2:
            closing_ppm2 = int(round(asking_ppm2 * (1 - margin_ratio)))
        if margin_ratio is not None and asking_price:
            closing_price = int(round(asking_price * (1 - margin_ratio)))

        transactions.append(
            MarketTransaction(
                id=f"alc-{row.get('gsraw_id', f'row-{index}')}",
                address=row.get("full_address") or row.get("admin4"),
                m2=area,
                bedrooms=(int(row["n_rooms"]) if row.get("n_rooms") is not None else None),
                bathrooms=(int(row["n_baths"]) if row.get("n_baths") is not None else None),
                asking_price=asking_price,
                closing_price=closing_price,
                asking_price_per_m2=asking_ppm2,
                closing_price_per_m2=closing_ppm2,
                negotiation_margin_pct=margin_pct,
                close_date=period_id,  # quarter label, e.g. "2025Q2"
                days_on_market=None,
                source="alicante-derived",
                distance_m=int(row["_distance_m"]) if row.get("_distance_m") is not None else None,
            )
        )

    return transactions


def _build_chart_series(
    transactions: list[MarketTransaction],
) -> list[MarketTransactionChartPoint]:
    series: list[MarketTransactionChartPoint] = []
    for index, txn in enumerate(transactions[:MAX_CHART_SERIES_ROWS], start=1):
        series.append(
            MarketTransactionChartPoint(
                label=_short_label(txn.address, index),
                asking_price=txn.asking_price,
                closing_price=txn.closing_price,
                negotiation_margin_pct=txn.negotiation_margin_pct,
            )
        )
    return series


def build_alicante_transactions(
    address: str,
    municipio: MunicipioInfo,
    *,
    m2: int,
    bedrooms: int,
    bathrooms: int,
    listing_avg_price_per_m2: Optional[int] = None,
) -> MarketTransactions:
    """Real-data market-transactions block for an Alicante valuation.

    Signature mirrors `build_market_transactions_mock` so the call sites in
    `routes.py` only need a conditional wrapper.

    Scope alignment
    ---------------
    Both the asking and the closing aggregates are computed at the same
    spatial scope (municipio-wide for residential apartments). This keeps
    `asking_vs_closing_gap_pct` and `negotiation_margin_pct` meaningful.
    The per-row transactions list uses listings around the property so the
    chart still has a "this neighborhood" feel.
    """
    closing_kpis = _fetch_closing_kpis()
    neighborhood_listings = _fetch_neighborhood_listings(municipio)
    asking_aggregates = storage.municipio_asking_aggregates(
        admin3=ALICANTE_ADMIN3_NAME,
        property_type="Pisos",
        operation_type="Venta",
    )

    # ── Closing side (official aggregates from Indicadores_Transacciones) ──
    closing_ppm2_row = (
        closing_kpis.get(INDICATOR_CLOSING_PPM2_AVG)
        or closing_kpis.get(INDICATOR_CLOSING_PPM2_MEDIAN)
    )
    closing_price_row = (
        closing_kpis.get(INDICATOR_CLOSING_PRICE_AVG)
        or closing_kpis.get(INDICATOR_CLOSING_PRICE_MEDIAN)
    )

    closing_ppm2 = (
        int(closing_ppm2_row["calculated_value"])
        if closing_ppm2_row and closing_ppm2_row.get("calculated_value") is not None
        else None
    )
    closing_price = (
        int(closing_price_row["calculated_value"])
        if closing_price_row and closing_price_row.get("calculated_value") is not None
        else None
    )
    period_id = _pick_period(closing_ppm2_row, closing_price_row)

    # ── Asking side (municipio-wide from alicante_listings) ────────────────
    # We deliberately use a municipio-wide aggregate (same scope as closing)
    # for the summary. `listing_avg_price_per_m2` is the LOCAL stat used by
    # the valuation engine; piping it in here would re-introduce the
    # apples-to-oranges mismatch.
    avg_asking_price = (
        int(asking_aggregates["avg_price"])
        if asking_aggregates.get("avg_price") is not None
        else None
    )
    avg_asking_ppm2 = (
        int(asking_aggregates["avg_ppm2"])
        if asking_aggregates.get("avg_ppm2") is not None
        else None
    )

    margin_pct = _derive_margin_pct(avg_asking_ppm2, closing_ppm2)
    gap_pct = margin_pct  # same calculation at this scope

    transactions = _build_synthetic_transactions(
        neighborhood_listings,
        margin_pct=margin_pct,
        period_id=period_id,
    )

    summary = MarketTransactionsSummary(
        total_transactions=len(transactions),
        avg_asking_price=avg_asking_price,
        avg_closing_price=closing_price,
        avg_asking_price_per_m2=avg_asking_ppm2,
        avg_closing_price_per_m2=closing_ppm2,
        asking_vs_closing_gap_pct=gap_pct,
        negotiation_margin_pct=margin_pct,
        sample_size=int(asking_aggregates.get("n") or 0),
        chart_series=_build_chart_series(transactions),
    )

    logger.info(
        "Alicante market-transactions: period=%s margin=%s%% avg_ask_ppm2=%s avg_close_ppm2=%s "
        "(asking_n=%d, neighborhood_n=%d)",
        period_id, margin_pct, avg_asking_ppm2, closing_ppm2,
        int(asking_aggregates.get("n") or 0), len(neighborhood_listings),
    )

    return MarketTransactions(summary=summary, transactions=transactions)


__all__ = ["build_alicante_transactions"]
