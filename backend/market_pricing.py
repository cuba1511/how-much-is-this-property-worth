"""
Median price-per-sqm lookup for Spanish municipalities.

The dataset lives in ``data/median_sqm_price.csv`` (3 rows per town:
``new_construction`` / ``second_hand`` / ``total``). For the comparables
valuation we use the ``second_hand`` row and its ``median_sqm_price_2026Q1``
column to compute a per-listing ``closing_value`` and ``negotiation_factor``.

Both the CSV ``town_name`` and the incoming ``municipio.name`` are normalized
(strip accents + lowercase) so casing/diacritic variants match.
"""

import csv
import logging
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "median_sqm_price.csv"

SECOND_HAND_CATEGORY = "second_hand"
PRICE_COLUMN = "median_sqm_price_2026Q1"


def _normalize(name: str) -> str:
    """Lowercase + strip accents. Whitespace and inner punctuation are kept."""
    decomposed = unicodedata.normalize("NFKD", name or "")
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return ascii_only.strip().lower()


@lru_cache(maxsize=1)
def _load_second_hand_prices() -> dict[str, float]:
    """Load the CSV once and return a {normalized_town_name: price} dict."""
    if not CSV_PATH.exists():
        logger.warning("Median sqm price CSV not found at %s", CSV_PATH)
        return {}

    prices: dict[str, float] = {}
    with CSV_PATH.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row.get("category") != SECOND_HAND_CATEGORY:
                continue
            raw_price = (row.get(PRICE_COLUMN) or "").strip()
            if not raw_price:
                continue
            try:
                price = float(raw_price)
            except ValueError:
                continue
            town_name = row.get("town_name") or ""
            key = _normalize(town_name)
            if not key:
                continue
            prices[key] = price

    logger.info(
        "Loaded median sqm prices for %d municipalities (category=%s, column=%s)",
        len(prices),
        SECOND_HAND_CATEGORY,
        PRICE_COLUMN,
    )
    return prices


def get_median_sqm_price(municipio_name: str) -> Optional[float]:
    """Return the second-hand 2026Q1 median EUR/m2 for a municipality, or None."""
    if not municipio_name:
        return None
    return _load_second_hand_prices().get(_normalize(municipio_name))
