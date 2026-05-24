"""Search + fetch logic for the `transactions` table in Airtable.

This is the data layer behind the coach UI (`/coach`). The frontend calls
the FastAPI proxy, which then talks to Airtable using the PAT held in
`backend/.env` (never exposed to the browser).

Field mapping (Airtable → API):

| Airtable column                                                                                   | API field            |
|---------------------------------------------------------------------------------------------------|----------------------|
| `Transaction Name`                                                                                | `transaction_name`   |
| `Address`                                                                                         | `address`            |
| `Client email`                                                                                    | `client_email`       |
| `Taxland number (from properties)`                                                                | `cadastral_reference`|
| `Type`                                                                                            | `type`               |
| `Beds`                                                                                            | `bedrooms`           |
| `Baths`                                                                                           | `bathrooms`          |
| `Landsize`                                                                                        | `landsize_m2`        |
| `Created_Date`                                                                                    | `created_at`         |
| `Country (from Properties)`                                                                       | filter only          |
| `Total est. costs (Reno + furniture + technical project costs + Apportionment Amount)`            | `total_est_costs`    |
| `Final Total Price (from Properties)`                                                             | `final_total_price`  |

Airtable returns lookup fields (like `Final Total Price (from Properties)`)
as arrays; we always pick the first non-null element so the API response is
flat and easy to consume from the React frontend.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from airtable.client import (
    AirtableAPIError,
    AirtableConfig,
    get_record,
    list_records,
)
from models import TransactionDetail, TransactionSummary

logger = logging.getLogger(__name__)

TRANSACTIONS_TABLE_ENV = "AIRTABLE_TRANSACTIONS_TABLE"
DEFAULT_TRANSACTIONS_TABLE = "Transactions"
TRANSACTIONS_VIEW_ENV = "AIRTABLE_TRANSACTIONS_VIEW"
DEFAULT_TRANSACTIONS_VIEW = "SP - AUM"

# Airtable column names. Kept as constants so the rename in Airtable (or a
# locale change) is a single-line patch instead of a project-wide grep.
FIELD_TRANSACTION_NAME = "Transaction Name"
FIELD_ADDRESS = "Address"
FIELD_CLIENT_EMAIL = "Client email"
FIELD_CADASTRAL_REFERENCE = "Taxland number (from properties)"
FIELD_TYPE = "Type"
FIELD_BEDS = "Beds"
FIELD_BATHS = "Baths"
FIELD_LANDSIZE = "Landsize"
FIELD_CREATED_AT = "Created_Date"
FIELD_COUNTRY = "Country (from Properties)"
FIELD_TOTAL_EST_COSTS = (
    "Total est. costs (Reno + furniture + technical project costs + Apportionment Amount)"
)
FIELD_FINAL_TOTAL_PRICE = "Final Total Price (from Properties)"

LIST_FIELDS: list[str] = [
    FIELD_TRANSACTION_NAME,
    FIELD_ADDRESS,
    FIELD_CLIENT_EMAIL,
    FIELD_CADASTRAL_REFERENCE,
    FIELD_TYPE,
    FIELD_BEDS,
    FIELD_BATHS,
    FIELD_LANDSIZE,
    FIELD_CREATED_AT,
    FIELD_TOTAL_EST_COSTS,
    FIELD_FINAL_TOTAL_PRICE,
]


def _table_name() -> str:
    return os.environ.get(TRANSACTIONS_TABLE_ENV, DEFAULT_TRANSACTIONS_TABLE).strip() or DEFAULT_TRANSACTIONS_TABLE


def _view_name() -> Optional[str]:
    value = os.environ.get(TRANSACTIONS_VIEW_ENV, DEFAULT_TRANSACTIONS_VIEW).strip()
    return value or None


def _flatten_lookup(value: Any) -> Any:
    """Airtable lookup fields come back as arrays even when single-valued.

    Picks the first non-null element so the API response is flat. Returns
    `None` when the array is empty or absent.
    """
    if isinstance(value, list):
        for item in value:
            if item is not None:
                return item
        return None
    return value


def _get_int(fields: dict[str, Any], key: str) -> Optional[int]:
    raw = _flatten_lookup(fields.get(key))
    if raw is None or raw == "":
        return None
    try:
        return int(round(float(raw)))
    except (TypeError, ValueError):
        return None


def _get_str(fields: dict[str, Any], key: str) -> Optional[str]:
    raw = _flatten_lookup(fields.get(key))
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _escape_formula_literal(value: str) -> str:
    """Escape a string for safe inclusion in an Airtable formula literal.

    Airtable uses single quotes for string literals; we double up any quotes
    inside the user-supplied query and strip control characters so the
    formula stays well-formed even when the search input contains weird
    pastes.
    """
    cleaned = "".join(ch for ch in value if ch.isprintable())
    return cleaned.replace("'", "\\'")


def _country_filter_formula() -> str:
    """Only return Spanish transactions.

    `Country (from Properties)` is a lookup field. Airtable formula equality
    works for the single-value lookup shape used here and is faster/clearer
    than scanning all lookup text.
    """
    return f"{{{FIELD_COUNTRY}}} = 'Spain'"


def _build_search_formula(query: str) -> str:
    """Case-insensitive substring match over Transaction Name.

    Airtable's `SEARCH(needle, haystack)` returns a number when found and
    blank otherwise — we wrap it in `OR()` so adding more searchable fields
    later (e.g. an `Address` column once it lands in the schema) is a
    one-line change.
    """
    needle = _escape_formula_literal(query.lower())
    search = f"OR(FIND('{needle}', LOWER({{{FIELD_TRANSACTION_NAME}}})))"
    return search if _view_name() else f"AND({_country_filter_formula()},{search})"


def _summary_from_record(record: dict[str, Any]) -> TransactionSummary:
    fields = record.get("fields", {}) or {}
    return TransactionSummary(
        id=record["id"],
        transaction_name=_get_str(fields, FIELD_TRANSACTION_NAME) or record["id"],
        address=_get_str(fields, FIELD_ADDRESS),
        client_email=_get_str(fields, FIELD_CLIENT_EMAIL),
        cadastral_reference=_get_str(fields, FIELD_CADASTRAL_REFERENCE),
        type=_get_str(fields, FIELD_TYPE),
        bedrooms=_get_int(fields, FIELD_BEDS),
        bathrooms=_get_int(fields, FIELD_BATHS),
        landsize_m2=_get_int(fields, FIELD_LANDSIZE),
        created_at=_get_str(fields, FIELD_CREATED_AT),
        total_est_costs=_get_int(fields, FIELD_TOTAL_EST_COSTS),
        final_total_price=_get_int(fields, FIELD_FINAL_TOTAL_PRICE),
    )


def _detail_from_record(record: dict[str, Any]) -> TransactionDetail:
    fields = record.get("fields", {}) or {}
    summary = _summary_from_record(record)
    return TransactionDetail(
        **summary.model_dump(),
        raw_fields=fields,
    )


async def search_transactions(
    *,
    config: AirtableConfig,
    query: str,
    max_results: int = 25,
) -> list[TransactionSummary]:
    """Server-side search against Airtable using `filterByFormula`.

    Empty query → return the most recent `max_results` transactions so the
    UI has something to render on first paint.
    """
    sort_clause = [{"field": FIELD_CREATED_AT, "direction": "desc"}]

    view = _view_name()
    formula = _build_search_formula(query.strip()) if query.strip() else None
    if not view and formula is None:
        formula = _country_filter_formula()
    records = await list_records(
        config=config,
        table=_table_name(),
        view=view,
        filter_formula=formula,
        fields=LIST_FIELDS,
        max_records=max_results,
        page_size=max_results,
        sort=sort_clause,
    )

    return [_summary_from_record(r) for r in records]


async def get_transaction(
    *,
    config: AirtableConfig,
    record_id: str,
) -> TransactionDetail:
    """Fetch a single transaction by Airtable record id.

    Re-raises `AirtableAPIError` so the route handler can map 404s to a
    proper HTTP 404 response.
    """
    record = await get_record(config=config, table=_table_name(), record_id=record_id)
    return _detail_from_record(record)


__all__ = [
    "AirtableAPIError",
    "search_transactions",
    "get_transaction",
]
