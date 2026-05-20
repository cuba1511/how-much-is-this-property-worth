"""Valuation-pipeline helpers — local copy for the Alicante MVP.

This is a deliberate duplication of the orchestration helpers that live in
`main.py` (`build_dataset`, `log_dataset`, `_choose_estimate`,
`_confidence_interval`). Keeping a local copy here means the Alicante MVP
package is fully self-contained: deleting `backend/alicante/` removes the
MVP entirely without touching production code.

When the MVP graduates, the obvious cleanup is to extract these helpers
into `backend/valuation/pipeline.py` (shared) and delete this file.
"""
from __future__ import annotations

import logging
import statistics
from typing import Optional

from models import ComparablesDataset, DatasetRow, Listing
from valuation.regression import predict_from_regression

logger = logging.getLogger(__name__)

# ── Tuning knobs (must mirror main.py until the MVP graduates) ───────────
DATASET_MAX_ROWS = 10
DATASET_MIN_ROWS = 3

OLS_MIN_SAMPLE_SIZE = 6
OLS_MIN_R_SQUARED = 0.5
OLS_VS_BASELINE_MAX_DEVIATION = 0.5  # 50%
CI_FLOOR_EUR = 0


def build_dataset(listings: list[Listing]) -> ComparablesDataset:
    rows: list[DatasetRow] = []
    for listing in listings[:DATASET_MAX_ROWS]:
        rows.append(
            DatasetRow(
                listing_url=listing.url,
                metros=listing.m2,
                precio=listing.price,
                habitaciones=listing.bedrooms,
                banos=listing.bathrooms,
            )
        )
    return ComparablesDataset(
        rows=rows,
        row_count=len(rows),
        min_required=DATASET_MIN_ROWS,
        max_allowed=DATASET_MAX_ROWS,
    )


def log_dataset(dataset: ComparablesDataset) -> None:
    logger.info("Comparables dataset (%d rows)", dataset.row_count)
    logger.info("| # | metros | precio | hab | banos |")
    logger.info("|---|--------|--------|-----|-------|")
    for idx, row in enumerate(dataset.rows, start=1):
        logger.info(
            "| %d | %s | %s | %s | %s |",
            idx,
            row.metros if row.metros is not None else "-",
            row.precio if row.precio is not None else "-",
            row.habitaciones if row.habitaciones is not None else "-",
            row.banos if row.banos is not None else "-",
        )
    if dataset.row_count < dataset.min_required:
        logger.warning(
            "Dataset has %d rows, below recommended minimum of %d",
            dataset.row_count,
            dataset.min_required,
        )


def choose_estimate(
    *,
    regression,
    baseline_estimate: Optional[int],
    m2: int,
    bedrooms: int,
    bathrooms: int,
) -> tuple[Optional[int], Optional[str]]:
    """Pick between the OLS prediction and the avg_ppm² × m² baseline.

    Mirrors `main._choose_estimate` — see that function for the full
    rationale. Kept as a separate copy for Alicante isolation.
    """
    if regression is None:
        return baseline_estimate, ("avg_ppm2" if baseline_estimate else None)

    if (
        regression.is_underdetermined
        or regression.r_squared is None
        or regression.r_squared < OLS_MIN_R_SQUARED
        or regression.sample_size < OLS_MIN_SAMPLE_SIZE
    ):
        return baseline_estimate, ("avg_ppm2" if baseline_estimate else None)

    ols_estimate = predict_from_regression(
        regression, m2=m2, bedrooms=bedrooms, bathrooms=bathrooms
    )
    if ols_estimate is None:
        return baseline_estimate, ("avg_ppm2" if baseline_estimate else None)

    if baseline_estimate:
        deviation = abs(ols_estimate - baseline_estimate) / baseline_estimate
        if deviation > OLS_VS_BASELINE_MAX_DEVIATION:
            return baseline_estimate, "avg_ppm2"

    return ols_estimate, "ols_lstsq"


def confidence_interval(
    *,
    estimated: Optional[int],
    avg_ppm2: Optional[int],
    ppms: list[int],
    request_m2: int,
) -> tuple[Optional[int], Optional[int], Optional[str]]:
    """Mirrors `main._confidence_interval`.

    With ≥3 comparables we report `(avg_ppm² ± 1σ) × m²`; otherwise a flat
    ±10% band so the UI always has something to display.
    """
    if estimated is None:
        return None, None, None

    if avg_ppm2 and len(ppms) >= 3:
        try:
            std_ppm2 = statistics.stdev(ppms)
        except statistics.StatisticsError:
            std_ppm2 = 0.0
        low = max(CI_FLOOR_EUR, int((avg_ppm2 - std_ppm2) * request_m2))
        high = int((avg_ppm2 + std_ppm2) * request_m2)
        if high > low:
            return low, high, "sample_std"

    return (
        int(estimated * 0.90),
        int(estimated * 1.10),
        "flat_pct",
    )


__all__ = [
    "DATASET_MAX_ROWS",
    "DATASET_MIN_ROWS",
    "build_dataset",
    "log_dataset",
    "choose_estimate",
    "confidence_interval",
]
