"""Thin HTTP client for the Airtable REST API.

We only talk to Airtable from the backend so the Personal Access Token (PAT)
never reaches the browser bundle. The client is intentionally minimal — we
expose a single `list_records()` helper and let the higher-level
`transactions.py` module compose the filter formulas it needs.

Docs: https://airtable.com/developers/web/api/list-records
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

AIRTABLE_API_BASE = "https://api.airtable.com/v0"
# Separate connect / read timeouts. Connect should be quick (DNS + TCP +
# TLS); the read budget is generous because Airtable can take a few seconds
# to assemble lookup-heavy responses when no `fields[]` projection is sent.
DEFAULT_CONNECT_TIMEOUT_S = 5.0
DEFAULT_READ_TIMEOUT_S = 30.0
_DEFAULT_TIMEOUT = httpx.Timeout(
    connect=DEFAULT_CONNECT_TIMEOUT_S,
    read=DEFAULT_READ_TIMEOUT_S,
    write=DEFAULT_READ_TIMEOUT_S,
    pool=DEFAULT_READ_TIMEOUT_S,
)
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.75


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

    logger.info(
        "Airtable list_records → table=%s view=%s filter=%s max=%s",
        table,
        view or "-",
        "yes" if filter_formula else "no",
        max_records,
    )
    started = time.monotonic()
    async with httpx.AsyncClient(
        timeout=_DEFAULT_TIMEOUT,
        trust_env=False,
    ) as client:
        response = await _get_with_retries(
            client=client,
            url=url,
            params=params,
            headers=headers,
            started=started,
            context=f"list_records table={table} max={max_records}",
        )

    elapsed = time.monotonic() - started
    if response.status_code >= 400:
        logger.warning(
            "Airtable list_records FAILED status=%s in %.2fs",
            response.status_code,
            elapsed,
        )
        raise AirtableAPIError(response.status_code, response.text)

    payload = response.json()
    records = payload.get("records", [])
    logger.info(
        "Airtable list_records ← %s records in %.2fs (table=%s)",
        len(records),
        elapsed,
        table,
    )
    return records


async def get_record(
    *,
    config: AirtableConfig,
    table: str,
    record_id: str,
    fields: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Fetch a single record by its Airtable record id (e.g. `rec...`)."""
    table_path = urllib.parse.quote(table, safe="")
    record_path = urllib.parse.quote(record_id, safe="")
    url = f"{AIRTABLE_API_BASE}/{config.base_id}/{table_path}/{record_path}"
    headers = {"Authorization": f"Bearer {config.pat}"}
    params: dict[str, Any] = {}
    if fields:
        for field in fields:
            params.setdefault("fields[]", [])
            params["fields[]"].append(field)

    started = time.monotonic()
    logger.info(
        "Airtable get_record → table=%s id=%s fields=%s",
        table,
        record_id,
        len(fields) if fields else "all",
    )
    async with httpx.AsyncClient(
        timeout=_DEFAULT_TIMEOUT,
        trust_env=False,
    ) as client:
        response = await _get_with_retries(
            client=client,
            url=url,
            params=params,
            headers=headers,
            started=started,
            context=f"get_record table={table} id={record_id}",
        )

    elapsed = time.monotonic() - started
    if response.status_code == 404:
        logger.info("Airtable get_record ← 404 in %.2fs (id=%s)", elapsed, record_id)
        raise AirtableAPIError(404, response.text)
    if response.status_code >= 400:
        logger.warning(
            "Airtable get_record FAILED status=%s in %.2fs",
            response.status_code,
            elapsed,
        )
        raise AirtableAPIError(response.status_code, response.text)

    logger.info("Airtable get_record ← OK in %.2fs (id=%s)", elapsed, record_id)
    return response.json()


async def _get_with_retries(
    *,
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, Any],
    headers: dict[str, str],
    started: float,
    context: str,
) -> httpx.Response:
    """GET with small retries for Airtable's intermittent 5xx/timeout spikes."""
    last_timeout: httpx.ReadTimeout | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await client.get(url, params=params, headers=headers)
        except httpx.ConnectError as exc:
            # On macOS, a process whose DNS resolver state is poisoned (commonly
            # because a VPN added unreachable resolvers via `scutil --dns`) will
            # fail every `getaddrinfo` with EAI_NONAME instantly until the worker
            # is restarted. Surface that as 502 so the UI shows a clear error
            # instead of timing out.
            if "nodename nor servname" in str(exc):
                logger.error(
                    "Airtable %s DNS resolution failed (process resolver poisoned"
                    " — disconnect VPN or restart uvicorn): %s",
                    context,
                    exc,
                )
                raise AirtableAPIError(
                    502,
                    "Airtable unreachable (macOS DNS resolver poisoned — disconnect VPN or restart backend)",
                ) from exc
            raise
        except httpx.ReadTimeout as exc:
            last_timeout = exc
            if attempt < MAX_ATTEMPTS:
                logger.warning(
                    "Airtable %s TIMEOUT on attempt %d/%d; retrying",
                    context,
                    attempt,
                    MAX_ATTEMPTS,
                )
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
                continue
            break

        if response.status_code in TRANSIENT_STATUS_CODES and attempt < MAX_ATTEMPTS:
            logger.warning(
                "Airtable %s returned transient status=%s on attempt %d/%d; retrying",
                context,
                response.status_code,
                attempt,
                MAX_ATTEMPTS,
            )
            await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
            continue
        return response

    elapsed = time.monotonic() - started
    logger.error("Airtable %s TIMEOUT after %.1fs", context, elapsed)
    raise AirtableAPIError(
        504,
        f"Airtable did not respond within {DEFAULT_READ_TIMEOUT_S:.0f}s",
    ) from last_timeout
