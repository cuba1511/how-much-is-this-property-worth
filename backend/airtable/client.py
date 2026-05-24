"""Thin HTTP client for the Airtable REST API.

We only talk to Airtable from the backend so the Personal Access Token (PAT)
never reaches the browser bundle. The client is intentionally minimal — we
expose a single `list_records()` helper and let the higher-level
`transactions.py` module compose the filter formulas it needs.

Docs: https://airtable.com/developers/web/api/list-records
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from dataclasses import dataclass
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

AIRTABLE_API_BASE = "https://api.airtable.com/v0"
DEFAULT_TIMEOUT_S = 15.0


class AirtableConfigError(RuntimeError):
    """Raised when AIRTABLE_PAT or AIRTABLE_BASE_ID is missing."""


class AirtableAPIError(RuntimeError):
    """Raised on a non-2xx response from Airtable. Wraps the status + body."""

    def __init__(self, status_code: int, body: str):
        super().__init__(f"Airtable API error {status_code}: {body[:200]}")
        self.status_code = status_code
        self.body = body


@dataclass(frozen=True)
class AirtableConfig:
    pat: str
    base_id: str

    @classmethod
    def from_env(cls) -> "AirtableConfig":
        pat = os.environ.get("AIRTABLE_PAT", "").strip()
        base_id = os.environ.get("AIRTABLE_BASE_ID", "").strip()
        if not pat or not base_id:
            raise AirtableConfigError(
                "AIRTABLE_PAT and AIRTABLE_BASE_ID must be set in backend/.env"
            )
        return cls(pat=pat, base_id=base_id)


async def list_records(
    *,
    config: AirtableConfig,
    table: str,
    view: Optional[str] = None,
    filter_formula: Optional[str] = None,
    fields: Optional[list[str]] = None,
    max_records: int = 25,
    page_size: int = 25,
    sort: Optional[list[dict[str, str]]] = None,
) -> list[dict[str, Any]]:
    """List records from a table, optionally filtered server-side.

    `filter_formula` uses Airtable's formula syntax (e.g. `SEARCH(...)` for
    case-insensitive substring matching). When omitted we just return the
    first `max_records` rows ordered by `sort` (or Airtable's default).
    """
    params: dict[str, Any] = {
        "maxRecords": max_records,
        "pageSize": page_size,
    }
    if view:
        params["view"] = view
    if filter_formula:
        params["filterByFormula"] = filter_formula
    if fields:
        for field in fields:
            params.setdefault("fields[]", [])
            params["fields[]"].append(field)
    if sort:
        for idx, entry in enumerate(sort):
            if "field" in entry:
                params[f"sort[{idx}][field]"] = entry["field"]
            if "direction" in entry:
                params[f"sort[{idx}][direction]"] = entry["direction"]

    table_path = urllib.parse.quote(table, safe="")
    url = f"{AIRTABLE_API_BASE}/{config.base_id}/{table_path}"
    headers = {"Authorization": f"Bearer {config.pat}"}

    # Force IPv4. On some local macOS/Python/httpx combinations Airtable's
    # IPv6 path stalls for ~10s before falling back, while curl and browsers
    # return in <1s. Pinning the local address keeps coach searches snappy.
    transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
    async with httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT_S,
        transport=transport,
        trust_env=False,
    ) as client:
        response = await client.get(url, params=params, headers=headers)
    if response.status_code >= 400:
        raise AirtableAPIError(response.status_code, response.text)

    payload = response.json()
    return payload.get("records", [])


async def get_record(
    *,
    config: AirtableConfig,
    table: str,
    record_id: str,
) -> dict[str, Any]:
    """Fetch a single record by its Airtable record id (e.g. `rec...`)."""
    table_path = urllib.parse.quote(table, safe="")
    record_path = urllib.parse.quote(record_id, safe="")
    url = f"{AIRTABLE_API_BASE}/{config.base_id}/{table_path}/{record_path}"
    headers = {"Authorization": f"Bearer {config.pat}"}

    transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
    async with httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT_S,
        transport=transport,
        trust_env=False,
    ) as client:
        response = await client.get(url, headers=headers)
    if response.status_code == 404:
        raise AirtableAPIError(404, response.text)
    if response.status_code >= 400:
        raise AirtableAPIError(response.status_code, response.text)

    return response.json()
