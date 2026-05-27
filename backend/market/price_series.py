"""Read-only access to the municipal €/m² price series shipped in SQLite.

The series is built by `backend/scripts/build_market_price_series.py` from
the TF Labs CSV export. At runtime this module exposes:

- :class:`PriceSeriesStore` — thin wrapper around a single SQLite connection.
- :func:`compute_appreciation` — turns a settlement date + resolved town
  into a :class:`models.MarketAppreciation` payload ready for the API.
- :func:`get_default_store` — lazily-opened module-level singleton so we
  share one connection across FastAPI workers.

Design choices:

- SQLite is opened with ``mode=ro`` so an accidental write attempt is loud
  instead of silently corrupting the dataset.
- The connection is created with ``check_same_thread=False`` because the
  FastAPI default thread pool runs handlers on multiple worker threads and
  SQLite's per-connection lock is enough for our read-only workload.
- Town resolution is intentionally additive: caller passes whichever
  identifiers they have (Airtable record id, INE code, municipality name)
  and the store tries them in that priority order.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from models import MarketAppreciation

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = REPO_ROOT / "backend" / "data" / "market_price_series.db"


class PriceSeriesError(RuntimeError):
    """Raised when the SQLite store is missing or unreadable."""


@dataclass(frozen=True)
class TownMatch:
    """One resolved municipality row from ``market_towns``."""

    town_id: str
    ine_code: str
    town_name: str
    province_id: Optional[str]
    community_id: Optional[str]
    resolution_strategy: str  # "airtable_town_id" | "ine_code" | "name_match"


def _normalize_name(name: str) -> str:
    """Same normalization used by the build script (lowercase + no accents)."""
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower().strip()


def _period_for(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _months_between(from_period: str, to_period: str) -> int:
    """Months between two ``YYYY-MM`` strings. Always >= 0."""
    fy, fm = (int(p) for p in from_period.split("-"))
    ty, tm = (int(p) for p in to_period.split("-"))
    return max(0, (ty - fy) * 12 + (tm - fm))


class PriceSeriesStore:
    """Read-only SQLite-backed store for the municipal price series."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self._db_path = db_path
        if not db_path.exists():
            raise PriceSeriesError(
                f"Market price series DB not found at {db_path}. "
                "Run `make build-market-series` to build it from the CSV."
            )
        # `mode=ro` makes the connection read-only at the driver level.
        uri = f"file:{db_path}?mode=ro"
        self._conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._latest_period_cache: Optional[str] = None

    # ── town resolution ────────────────────────────────────────────────

    def resolve_town(
        self,
        *,
        airtable_record_id: Optional[str] = None,
        ine_code: Optional[str] = None,
        name: Optional[str] = None,
        province_id: Optional[str] = None,
    ) -> Optional[TownMatch]:
        """Find one ``market_towns`` row using whichever identifiers we have.

        Priority: explicit Airtable record id → INE code → normalized name.
        ``province_id`` narrows the name search when the same name exists in
        several provinces (e.g. there are multiple "Cabezón").
        """
        with self._lock:
            if airtable_record_id:
                row = self._conn.execute(
                    "SELECT * FROM market_towns WHERE town_id = ? LIMIT 1",
                    (airtable_record_id,),
                ).fetchone()
                if row:
                    return self._row_to_match(row, "airtable_town_id")

            if ine_code:
                row = self._conn.execute(
                    "SELECT * FROM market_towns WHERE ine_code = ? LIMIT 1",
                    (ine_code,),
                ).fetchone()
                if row:
                    return self._row_to_match(row, "ine_code")

            if name:
                normalized = _normalize_name(name)
                if not normalized:
                    return None
                if province_id:
                    row = self._conn.execute(
                        "SELECT * FROM market_towns WHERE town_name_norm = ? "
                        "AND province_id = ? LIMIT 1",
                        (normalized, province_id),
                    ).fetchone()
                    if row:
                        return self._row_to_match(row, "name_match")
                row = self._conn.execute(
                    "SELECT * FROM market_towns WHERE town_name_norm = ? LIMIT 1",
                    (normalized,),
                ).fetchone()
                if row:
                    return self._row_to_match(row, "name_match")

                # Bilingual fallback: TF Labs stores some municipalities under
                # a slashed "Castilian/Catalan" form (e.g. "Almazora/Almassora").
                # We try LIKE matches against either side of the slash before
                # giving up so coaches see appreciation data for the same town
                # the geocoder returned in plain Castilian or Catalan.
                like_prefix = f"{normalized}/%"
                like_suffix = f"%/{normalized}"
                if province_id:
                    row = self._conn.execute(
                        "SELECT * FROM market_towns WHERE province_id = ? "
                        "AND (town_name_norm LIKE ? OR town_name_norm LIKE ?) LIMIT 1",
                        (province_id, like_prefix, like_suffix),
                    ).fetchone()
                    if row:
                        return self._row_to_match(row, "name_match")
                row = self._conn.execute(
                    "SELECT * FROM market_towns "
                    "WHERE town_name_norm LIKE ? OR town_name_norm LIKE ? LIMIT 1",
                    (like_prefix, like_suffix),
                ).fetchone()
                if row:
                    return self._row_to_match(row, "name_match")

        return None

    @staticmethod
    def _row_to_match(row: sqlite3.Row, strategy: str) -> TownMatch:
        return TownMatch(
            town_id=row["town_id"],
            ine_code=row["ine_code"],
            town_name=row["town_name"],
            province_id=row["province_id"],
            community_id=row["community_id"],
            resolution_strategy=strategy,
        )

    # ── series lookups ────────────────────────────────────────────────

    def latest_period(self) -> Optional[str]:
        """Most recent period across the whole dataset (cached)."""
        if self._latest_period_cache is None:
            with self._lock:
                row = self._conn.execute(
                    "SELECT MAX(period) FROM market_price_series"
                ).fetchone()
            self._latest_period_cache = row[0] if row else None
        return self._latest_period_cache

    def value_at(self, town_id: str, period: str) -> Optional[tuple[str, float]]:
        """Value at ``period``, or the closest available period ≤ ``period``.

        Returns ``(actual_period, value)`` or ``None`` if the town has no
        data at or before that period. We never look forward: pulling a
        future month as "settlement value" would inflate apparent gains.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT period, value FROM market_price_series "
                "WHERE town_id = ? AND period <= ? "
                "ORDER BY period DESC LIMIT 1",
                (town_id, period),
            ).fetchone()
            if row:
                return row["period"], row["value"]
            # Fallback: if settlement is before our coverage, anchor at the
            # earliest available period so the report still has *some* baseline.
            row = self._conn.execute(
                "SELECT period, value FROM market_price_series "
                "WHERE town_id = ? ORDER BY period ASC LIMIT 1",
                (town_id,),
            ).fetchone()
            if row:
                return row["period"], row["value"]
        return None

    def latest_value(self, town_id: str) -> Optional[tuple[str, float]]:
        """Most recent observation for a town."""
        with self._lock:
            row = self._conn.execute(
                "SELECT period, value FROM market_price_series "
                "WHERE town_id = ? ORDER BY period DESC LIMIT 1",
                (town_id,),
            ).fetchone()
        if not row:
            return None
        return row["period"], row["value"]

    # ── lifecycle ──────────────────────────────────────────────────────

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# ── module-level singleton ────────────────────────────────────────────────

_default_store: Optional[PriceSeriesStore] = None
_default_store_lock = threading.Lock()


def get_default_store(db_path: Path = DEFAULT_DB_PATH) -> Optional[PriceSeriesStore]:
    """Lazy global accessor. Returns ``None`` (and logs once) if the DB is
    missing — the API stays up, the feature degrades gracefully.
    """
    global _default_store
    if _default_store is not None:
        return _default_store
    with _default_store_lock:
        if _default_store is not None:
            return _default_store
        try:
            _default_store = PriceSeriesStore(db_path)
            logger.info("Market price series store ready (%s)", db_path)
        except PriceSeriesError as exc:
            logger.warning("Market price series unavailable: %s", exc)
            _default_store = None
    return _default_store


# ── high-level helper used by the API layer ───────────────────────────────


def compute_appreciation(
    *,
    store: PriceSeriesStore,
    town: TownMatch,
    settlement_date: date,
) -> Optional[MarketAppreciation]:
    """Build a :class:`MarketAppreciation` payload for the report.

    Returns ``None`` when the town has no usable observations.
    """
    settlement_period = _period_for(settlement_date)

    from_pair = store.value_at(town.town_id, settlement_period)
    latest_pair = store.latest_value(town.town_id)
    if not from_pair or not latest_pair:
        return None

    from_period, from_value = from_pair
    to_period, to_value = latest_pair

    if from_value <= 0:
        return None

    pct_change = (to_value - from_value) / from_value
    months_elapsed = _months_between(from_period, to_period)
    annualized: Optional[float] = None
    if months_elapsed >= 12:
        try:
            annualized = (1 + pct_change) ** (12 / months_elapsed) - 1
        except (OverflowError, ValueError):
            annualized = None

    sample_quality = "exact" if from_period == settlement_period else "nearest_available"

    return MarketAppreciation(
        town_id=town.town_id,
        town_name=town.town_name,
        ine_code=town.ine_code,
        settlement_date=settlement_date.isoformat(),
        from_period=from_period,
        from_eur_per_m2=round(from_value, 2),
        to_period=to_period,
        to_eur_per_m2=round(to_value, 2),
        pct_change=round(pct_change, 4),
        annualized_pct_change=round(annualized, 4) if annualized is not None else None,
        months_elapsed=months_elapsed,
        sample_quality=sample_quality,
        resolution_strategy=town.resolution_strategy,
    )
