"""Valuation logic — OLS regression on comparables + market-transaction mock layer.

Pure-ish business code: no I/O, no network. Takes structured comparables and
returns numbers.
"""

from valuation.regression import (
    fit_listing_regression,
    predict_from_regression,
)
from valuation.market_transactions import build_market_transactions_mock

__all__ = [
    "fit_listing_regression",
    "predict_from_regression",
    "build_market_transactions_mock",
]
