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
| `Stage`                                                                                           | filter only          |
| `Price`                                                                                           | `price`              |
| `Final reno cost`                                                                                 | `final_reno_cost`    |
| `Final furniture cost`                                                                            | `final_furniture_cost` |
| `Technical project cost(s)`                                                                       | `technical_project_costs` |
| `Home appliances cost`                                                                            | `home_appliances_cost` |
| `Cleaning cost`                                                                                   | `cleaning_cost`      |
| `Real estate agent fee`                                                                           | `real_estate_agent_fee` |
| `Land registry cost`                                                                              | `land_registry_cost` |
| `PropHero fee`                                                                                    | `prophero_fee`       |
| `Notary cost`                                                                                     | `notary_cost`        |
| `Insurance`                                                                                       | `insurance`          |
| `Council rate`                                                                                    | `council_rate`       |
| `Service charges`                                                                                 | `service_charges`    |
| `Final total price`                                                                               | `final_total_price`  |

Airtable lookup fields may come back as arrays; we always pick the first
non-null element so the API response is flat and easy to consume from the
React frontend.
"""

from __future__ import annotations

import json
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

# Airtable column names. Some production fields have changed singular/plural or
# lookup suffixes over time, so optional financial columns are read through
# aliases and are not passed as an explicit `fields[]` projection.
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
FIELD_STAGE = "Stage"
TARGET_COUNTRY = "Spain"
TARGET_STAGE = "Property leased"
FIELD_PRICE = "Price"
FIELD_FINAL_RENO_COST = "Final reno cost"
FIELD_FINAL_FURNITURE_COST = "Final furniture cost"
FIELDS_TECHNICAL_PROJECT_COSTS = ["Technical project costs", "Technical project cost"]
FIELD_HOME_APPLIANCES_COST = "Home appliances cost"
FIELD_CLEANING_COST = "Cleaning cost"
FIELD_REAL_ESTATE_AGENT_FEE = "Real estate agent fee"
FIELD_LAND_REGISTRY_COST = "Land registry cost"
FIELD_PROPHERO_FEE = "PropHero fee"
FIELD_NOTARY_COST = "Notary cost"
FIELD_INSURANCE = "Insurance"
FIELD_COUNCIL_RATE = "Council rate"
FIELD_SERVICE_CHARGES = "Service charges"
FIELDS_FINAL_TOTAL_PRICE = [
    "Final total price",
    "Final Total Price",
    "Final Total Price (from Properties)",
]
# Real settlement date — the day the buyer paid the seller and took possession.
# This is the acquisition anchor used by the market-appreciation lookup.
FIELDS_REAL_SETTLEMENT_DATE = [
    "Real settlement date",
    "Real Settlement Date",
    "Real settlement date (from Properties)",
]
# Optional town reference. Coaches don't always fill this in; the price-series
# layer also resolves towns by municipality name as a fallback.
FIELDS_TOWN_RECORD_ID = [
    "Town",
    "Town (from Properties)",
    "Towns (from Properties)",
]

LIST_FIELDS: Optional[list[str]] = None
VALUATION_FIELDS: list[str] = [
    FIELD_TRANSACTION_NAME,
    FIELD_ADDRESS,
    FIELD_CLIENT_EMAIL,
    FIELD_CADASTRAL_REFERENCE,
    FIELD_TYPE,
    FIELD_BEDS,
    FIELD_BATHS,
    FIELD_LANDSIZE,
    FIELD_CREATED_AT,
    FIELD_PRICE,
    FIELD_FINAL_RENO_COST,
    FIELD_FINAL_FURNITURE_COST,
    *FIELDS_TECHNICAL_PROJECT_COSTS,
    FIELD_HOME_APPLIANCES_COST,
    FIELD_CLEANING_COST,
    FIELD_REAL_ESTATE_AGENT_FEE,
    FIELD_LAND_REGISTRY_COST,
    FIELD_PROPHERO_FEE,
    FIELD_NOTARY_COST,
    FIELD_INSURANCE,
    FIELD_COUNCIL_RATE,
    FIELD_SERVICE_CHARGES,
    *FIELDS_FINAL_TOTAL_PRICE,
    *FIELDS_REAL_SETTLEMENT_DATE,
    *FIELDS_TOWN_RECORD_ID,
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


def _get_int_any(fields: dict[str, Any], keys: list[str]) -> Optional[int]:
    for key in keys:
        value = _get_int(fields, key)
        if value is not None:
            return value
    return None


def _get_str(fields: dict[str, Any], key: str) -> Optional[str]:
    raw = _flatten_lookup(fields.get(key))
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _get_str_any(fields: dict[str, Any], keys: list[str]) -> Optional[str]:
    for key in keys:
        value = _get_str(fields, key)
        if value is not None:
            return value
    return None


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _unknown_requested_fields(error_body: str, requested_fields: list[str]) -> list[str]:
    """Best-effort extraction of Airtable 422 unknown field names.

    Airtable includes the missing field names in the JSON error message. We
    avoid depending on exact punctuation and only remove names that were in our
    request and appear verbatim in the upstream response.
    """
    try:
        payload = json.loads(error_body)
        message = str(payload.get("error", {}).get("message", ""))
    except (TypeError, ValueError):
        message = error_body
    return [field for field in requested_fields if field in message]


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
    return f"{{{FIELD_COUNTRY}}} = '{TARGET_COUNTRY}'"


def _stage_filter_formula() -> str:
    """Only return transactions ready for the coach report."""
    return f"{{{FIELD_STAGE}}} = '{TARGET_STAGE}'"


def _base_filter_formula() -> str:
    return f"AND({_country_filter_formula()},{_stage_filter_formula()})"


def _build_search_formula(query: str) -> str:
    """Case-insensitive substring match over Transaction Name.

    Airtable's `SEARCH(needle, haystack)` returns a number when found and
    blank otherwise — we wrap it in `OR()` so adding more searchable fields
    later (e.g. an `Address` column once it lands in the schema) is a
    one-line change.
    """
    needle = _escape_formula_literal(query.lower())
    search = f"OR(FIND('{needle}', LOWER({{{FIELD_TRANSACTION_NAME}}})))"
    return f"AND({_base_filter_formula()},{search})"


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
        price=_get_int(fields, FIELD_PRICE),
        final_reno_cost=_get_int(fields, FIELD_FINAL_RENO_COST),
        final_furniture_cost=_get_int(fields, FIELD_FINAL_FURNITURE_COST),
        technical_project_costs=_get_int_any(fields, FIELDS_TECHNICAL_PROJECT_COSTS),
        home_appliances_cost=_get_int(fields, FIELD_HOME_APPLIANCES_COST),
        cleaning_cost=_get_int(fields, FIELD_CLEANING_COST),
        real_estate_agent_fee=_get_int(fields, FIELD_REAL_ESTATE_AGENT_FEE),
        land_registry_cost=_get_int(fields, FIELD_LAND_REGISTRY_COST),
        prophero_fee=_get_int(fields, FIELD_PROPHERO_FEE),
        notary_cost=_get_int(fields, FIELD_NOTARY_COST),
        insurance=_get_int(fields, FIELD_INSURANCE),
        council_rate=_get_int(fields, FIELD_COUNCIL_RATE),
        service_charges=_get_int(fields, FIELD_SERVICE_CHARGES),
        final_total_price=_get_int_any(fields, FIELDS_FINAL_TOTAL_PRICE),
        real_settlement_date=_get_str_any(fields, FIELDS_REAL_SETTLEMENT_DATE),
        town_record_id=_get_str_any(fields, FIELDS_TOWN_RECORD_ID),
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

    Empty query → return the oldest leased Spanish transactions so the UI has
    the exact coach worklist on first paint.
    """
    sort_clause = [{"field": FIELD_CREATED_AT, "direction": "asc"}]

    view = _view_name()
    formula = _build_search_formula(query.strip()) if query.strip() else _base_filter_formula()
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


async def get_transaction_for_valuation(
    *,
    config: AirtableConfig,
    record_id: str,
) -> TransactionDetail:
    """Fetch one transaction with only the fields needed to build a report.

    Full Airtable rows include lookup-heavy blobs under `raw_fields`; fetching
    those again during report generation can trigger Airtable 504s. This path
    keeps the response small and drops stale optional aliases if Airtable says a
    projected field no longer exists.
    """
    requested_fields = _dedupe(VALUATION_FIELDS)
    while requested_fields:
        try:
            record = await get_record(
                config=config,
                table=_table_name(),
                record_id=record_id,
                fields=requested_fields,
            )
            return _detail_from_record(record)
        except AirtableAPIError as exc:
            if exc.status_code != 422:
                raise
            unknown_fields = _unknown_requested_fields(exc.body, requested_fields)
            if not unknown_fields:
                logger.warning(
                    "Airtable projected valuation fetch failed with 422 but no"
                    " unknown fields could be parsed; falling back to full row"
                )
                break
            logger.info(
                "Airtable projected valuation fetch dropping unknown fields: %s",
                ", ".join(unknown_fields),
            )
            requested_fields = [
                field for field in requested_fields if field not in unknown_fields
            ]

    record = await get_record(config=config, table=_table_name(), record_id=record_id)
    return _detail_from_record(record)


__all__ = [
    "AirtableAPIError",
    "search_transactions",
    "get_transaction",
    "get_transaction_for_valuation",
]
