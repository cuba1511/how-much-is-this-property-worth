"""Multiple linear regression on the comparables dataset.

Model (OLS with intercept):

    precio = a + b1*metros + b2*habitaciones + b3*banos

Solved via `numpy.linalg.lstsq` on the design matrix `X = [1, metros, hab, banos]`.
With n=10 comparables and p=4 free parameters (intercept + 3 features) the
system is well-determined and we report standard in-sample R^2.

Missing values for `habitaciones` / `banos` are imputed with the column median.
Missing `metros` or `precio` filters the row out (those are essential).

The output `coefficients` list is ordered: intercept first, then the three
features. The frontend iterates over them to compute the personalized
prediction (mapping each `feature` name to the corresponding user input,
treating `intercept` as the constant 1).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from statistics import median
from typing import Optional

import numpy as np

from models import DatasetRow, RegressionCoefficient, RegressionResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _FeatureSpec:
    name: str           # DatasetRow attribute
    label: str          # human-friendly label for the UI
    kind: str           # "intercept" | "continuous"
    unit_label: Optional[str] = None  # only relevant for "continuous"
    impute: bool = False  # impute missing values with column median


FEATURES: list[_FeatureSpec] = [
    _FeatureSpec("metros", "Por m²", "continuous", "m²", impute=False),
    _FeatureSpec("habitaciones", "Por habitación", "continuous", "habitación", impute=True),
    _FeatureSpec("banos", "Por baño", "continuous", "baño", impute=True),
]

INTERCEPT_SPEC = _FeatureSpec(
    "intercept", "Precio base (intercepto)", "intercept", None, impute=False
)

MIN_ROWS = 2


def _column_median(rows: list[DatasetRow], attr: str) -> Optional[float]:
    values = [getattr(r, attr) for r in rows if getattr(r, attr) is not None]
    if not values:
        return None
    return float(median(values))


def fit_listing_regression(rows: list[DatasetRow]) -> Optional[RegressionResult]:
    """Fit OLS with intercept on the comparables dataset.

    Returns None if there is not enough usable data.
    """

    if not rows:
        logger.info("Regression skipped: empty dataset")
        return None

    valid = [r for r in rows if r.precio is not None and r.metros is not None]
    if len(valid) < MIN_ROWS:
        logger.warning(
            "Regression skipped: only %d valid rows (need >= %d)",
            len(valid),
            MIN_ROWS,
        )
        return None

    medians: dict[str, Optional[float]] = {}
    for spec in FEATURES:
        if spec.impute:
            medians[spec.name] = _column_median(valid, spec.name)

    feature_rows: list[list[float]] = []
    prices: list[float] = []
    for row in valid:
        # Intercept column.
        x_row: list[float] = [1.0]
        for spec in FEATURES:
            raw = getattr(row, spec.name)
            if raw is None:
                if spec.impute:
                    fallback = medians.get(spec.name)
                    x_row.append(float(fallback) if fallback is not None else 0.0)
                else:
                    x_row.append(0.0)
            else:
                x_row.append(float(raw))
        feature_rows.append(x_row)
        prices.append(float(row.precio))

    X = np.array(feature_rows, dtype=float)
    y = np.array(prices, dtype=float)
    p = X.shape[1]  # intercept + 3 features

    b, _residuals, rank, _sv = np.linalg.lstsq(X, y, rcond=None)
    is_underdetermined = int(rank) < p

    y_pred = X @ b
    ss_res = float(np.sum((y - y_pred) ** 2))
    y_mean = float(np.mean(y))
    ss_tot = float(np.sum((y - y_mean) ** 2))
    if ss_tot > 0:
        r_squared: Optional[float] = 1.0 - ss_res / ss_tot
    else:
        r_squared = None

    intercept_value = float(b[0]) if math.isfinite(float(b[0])) else 0.0
    coefficients: list[RegressionCoefficient] = [
        RegressionCoefficient(
            feature=INTERCEPT_SPEC.name,
            label=INTERCEPT_SPEC.label,
            kind=INTERCEPT_SPEC.kind,
            unit_label=INTERCEPT_SPEC.unit_label,
            coefficient=intercept_value,
        )
    ]
    for spec, value in zip(FEATURES, b[1:]):
        safe_value = float(value) if math.isfinite(float(value)) else 0.0
        coefficients.append(
            RegressionCoefficient(
                feature=spec.name,
                label=spec.label,
                kind=spec.kind,
                unit_label=spec.unit_label,
                coefficient=safe_value,
            )
        )

    notes = (
        f"OLS con intercepto via numpy.linalg.lstsq. "
        f"R^2 in-sample (n={len(valid)}, p={p})."
    )

    return RegressionResult(
        method="ols_lstsq",
        coefficients=coefficients,
        sample_size=len(valid),
        feature_count=len(FEATURES),
        is_underdetermined=is_underdetermined,
        r_squared=r_squared,
        alpha=None,
        notes=notes,
    )


def predict_from_regression(
    result: RegressionResult,
    *,
    m2: Optional[int],
    bedrooms: Optional[int],
    bathrooms: Optional[int],
) -> Optional[int]:
    """Apply fitted OLS coefficients to a target property.

    Returns the predicted price in EUR, or `None` if the prediction is not
    safe to emit (non-finite, negative, or any required input missing).

    Maps each coefficient `feature` name back to the user input. `intercept`
    always contributes `1 * coefficient`. Missing inputs for continuous
    features short-circuit to None — we don't silently impute at predict time
    (the caller should fall back to the simpler `avg_ppm² × m²` baseline).
    """
    if result is None or m2 is None:
        return None

    inputs: dict[str, float] = {
        "metros": float(m2),
        "habitaciones": float(bedrooms) if bedrooms is not None else None,  # type: ignore[assignment]
        "banos": float(bathrooms) if bathrooms is not None else None,  # type: ignore[assignment]
    }

    total = 0.0
    for coef in result.coefficients:
        if coef.feature == "intercept":
            total += coef.coefficient
            continue
        value = inputs.get(coef.feature)
        if value is None:
            return None
        total += coef.coefficient * value

    if not math.isfinite(total) or total <= 0:
        return None
    return int(round(total))
