"""Market data layer.

Wraps the offline data sources we ship in `backend/data/` (currently the TF
Labs `SALE_PRICE_SQM_P50_SMOOTH` series). Pure-Python, no I/O beyond SQLite.
"""

from market.price_series import (
    PriceSeriesError,
    PriceSeriesStore,
    TownMatch,
    compute_appreciation,
    get_default_store,
)

__all__ = [
    "PriceSeriesError",
    "PriceSeriesStore",
    "TownMatch",
    "compute_appreciation",
    "get_default_store",
]
