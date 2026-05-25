"""Airtable integration — coach-facing transactions lookup.

Exposes a thin layer on top of the Airtable REST API so the FastAPI routes
in `main.py` stay readable. The Personal Access Token never leaves the
backend; the frontend talks exclusively to `/api/coach/*`.
"""

from airtable.client import (
    AirtableAPIError,
    AirtableConfig,
    AirtableConfigError,
)
from airtable.transactions import (
    get_transaction,
    get_transaction_for_valuation,
    search_transactions,
)

__all__ = [
    "AirtableAPIError",
    "AirtableConfig",
    "AirtableConfigError",
    "get_transaction",
    "get_transaction_for_valuation",
    "search_transactions",
]
