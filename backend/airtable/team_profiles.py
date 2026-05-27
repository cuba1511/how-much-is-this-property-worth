"""Cache + lookup for the Airtable `Team Profiles` table.

The transactions table exposes `Coach` and `Account Manager` as lookup fields
that resolve to record IDs in the `Team Profiles` table (e.g. ``recU1J…``).
To show human-readable names in the coach UI we need to resolve those IDs to
``{name, email}`` tuples.

Design choices:

- We cache the full `Team Profiles` table in memory (~hundreds of rows) keyed
  by record id. Hitting Airtable once per page-load of the transactions list
  would multiply our API budget by 25-100; hitting it once per process is
  cheap and good enough for an internal tool.
- TTL refresh (default 30 minutes) keeps the cache reasonably fresh without
  hammering Airtable. The cache refreshes lazily on the next request after
  expiry — there is no background task.
- The cache is async-safe through a single ``asyncio.Lock`` so concurrent
  coach requests don't trigger N parallel fetches on cold-start.
- Failures are logged and yield an empty cache so the UI degrades gracefully
  (rows render without a coach name instead of 500-ing).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Iterable, Optional

import httpx

from airtable.client import (
    AIRTABLE_API_BASE,
    AirtableAPIError,
    AirtableConfig,
    _DEFAULT_TIMEOUT,
    _get_with_retries,
)

logger = logging.getLogger(__name__)

TEAM_PROFILES_TABLE_ENV = "AIRTABLE_TEAM_PROFILES_TABLE"
DEFAULT_TEAM_PROFILES_TABLE = "Team Profiles"
CACHE_TTL_SECONDS = 30 * 60  # 30 minutes


@dataclass(frozen=True)
class TeamProfile:
    """One row from the Airtable `Team Profiles` table.

    Only the fields the coach UI cares about are typed; everything else is
    discarded to keep the cache small.
    """

    record_id: str
    name: str
    email: Optional[str] = None
    role: Optional[str] = None
    team: Optional[str] = None


_cache: dict[str, TeamProfile] = {}
_cache_loaded_at: float = 0.0
_cache_lock = asyncio.Lock()


def _table_name() -> str:
    value = os.environ.get(TEAM_PROFILES_TABLE_ENV, DEFAULT_TEAM_PROFILES_TABLE).strip()
    return value or DEFAULT_TEAM_PROFILES_TABLE


def _first(value: Any) -> Any:
    """Airtable returns single-value cells as scalars and lookups as arrays.

    Pick the first non-null element, otherwise return the scalar unchanged.
    """
    if isinstance(value, list):
        for item in value:
            if item not in (None, ""):
                return item
        return None
    return value


def _profile_from_record(record: dict[str, Any]) -> TeamProfile:
    fields = record.get("fields", {}) or {}
    name_raw = _first(fields.get("Name")) or _first(fields.get("Full Name"))
    name = str(name_raw).strip() if name_raw else record["id"]
    email_raw = _first(fields.get("Email"))
    role_raw = _first(fields.get("Role"))
    team_raw = _first(fields.get("Team/division") or fields.get("Team"))
    return TeamProfile(
        record_id=record["id"],
        name=name,
        email=str(email_raw).strip() if email_raw else None,
        role=str(role_raw).strip() if role_raw else None,
        team=str(team_raw).strip() if team_raw else None,
    )


async def _fetch_all(config: AirtableConfig) -> dict[str, TeamProfile]:
    """Page through the Team Profiles table and build a record_id → TeamProfile map.

    Uses raw httpx + the shared retry helper so we can handle pagination here
    (the `list_records` helper in `client.py` doesn't follow `offset`).
    """
    table_path = urllib.parse.quote(_table_name(), safe="")
    url = f"{AIRTABLE_API_BASE}/{config.base_id}/{table_path}"
    headers = {"Authorization": f"Bearer {config.pat}"}
    # We only care about the fields the UI surfaces. Restricting the projection
    # keeps the response small and survives stray column renames in Airtable.
    base_params: dict[str, Any] = {
        "pageSize": 100,
        "fields[]": ["Name", "Email", "Role", "Team/division"],
    }

    profiles: dict[str, TeamProfile] = {}
    offset: Optional[str] = None
    page_count = 0
    started = time.monotonic()
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT, trust_env=False) as client:
        while True:
            params = dict(base_params)
            if offset:
                params["offset"] = offset
            response = await _get_with_retries(
                client=client,
                url=url,
                params=params,
                headers=headers,
                started=started,
                context=f"team_profiles page={page_count}",
            )
            if response.status_code >= 400:
                raise AirtableAPIError(response.status_code, response.text)
            payload = response.json()
            for record in payload.get("records", []):
                profile = _profile_from_record(record)
                profiles[profile.record_id] = profile
            offset = payload.get("offset")
            page_count += 1
            if not offset or page_count > 20:  # 20 × 100 = 2000 — way more than we have
                break

    elapsed = time.monotonic() - started
    logger.info(
        "Airtable team_profiles cache primed: %d profiles in %.2fs (pages=%d)",
        len(profiles),
        elapsed,
        page_count,
    )
    return profiles


async def get_team_profiles(
    *, config: AirtableConfig, force_refresh: bool = False
) -> dict[str, TeamProfile]:
    """Return the cached record_id → TeamProfile map, refreshing if stale.

    The cache is shared across all coroutines and refreshed under a lock so we
    never have two concurrent requests fetching the same data on cold-start.
    """
    global _cache, _cache_loaded_at
    now = time.monotonic()
    fresh = (
        not force_refresh
        and bool(_cache)
        and (now - _cache_loaded_at) < CACHE_TTL_SECONDS
    )
    if fresh:
        return _cache

    async with _cache_lock:
        # Double-check inside the lock: another coroutine may have refreshed
        # the cache while we were waiting.
        now = time.monotonic()
        fresh = (
            not force_refresh
            and bool(_cache)
            and (now - _cache_loaded_at) < CACHE_TTL_SECONDS
        )
        if fresh:
            return _cache
        try:
            _cache = await _fetch_all(config)
            _cache_loaded_at = now
        except (AirtableAPIError, httpx.HTTPError) as exc:
            # Degrade gracefully: keep the stale cache (or empty dict) so the
            # transactions endpoint doesn't 500 just because we can't refresh.
            logger.warning("Team Profiles cache refresh failed: %s", exc)
            if not _cache:
                _cache = {}
    return _cache


async def resolve_profile(
    *, config: AirtableConfig, record_id: Optional[str]
) -> Optional[TeamProfile]:
    """Resolve a single record id to a :class:`TeamProfile`, or ``None``."""
    if not record_id:
        return None
    profiles = await get_team_profiles(config=config)
    return profiles.get(record_id)


async def resolve_profiles(
    *, config: AirtableConfig, record_ids: Iterable[Optional[str]]
) -> dict[str, TeamProfile]:
    """Bulk-resolve a set of record ids. Returns only the ones we recognised."""
    ids = {rid for rid in record_ids if rid}
    if not ids:
        return {}
    profiles = await get_team_profiles(config=config)
    return {rid: profiles[rid] for rid in ids if rid in profiles}


__all__ = [
    "TeamProfile",
    "get_team_profiles",
    "resolve_profile",
    "resolve_profiles",
]
