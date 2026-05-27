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
from airtable.team_profiles import (
    TeamProfile,
    get_team_profiles,
    resolve_profile,
    resolve_profiles,
)
from airtable.transactions import (
    enrich_with_coach_owners,
    get_transaction,
    get_transaction_for_valuation,
    search_transactions,
    search_transactions_page,
)

__all__ = [
    "AirtableAPIError",
    "AirtableConfig",
    "AirtableConfigError",
    "TeamProfile",
    "enrich_with_coach_owners",
    "get_team_profiles",
    "get_transaction",
    "get_transaction_for_valuation",
    "resolve_profile",
    "resolve_profiles",
    "search_transactions",
    "search_transactions_page",
]
