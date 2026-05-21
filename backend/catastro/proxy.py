"""Bright Data fallback for Catastro requests.

Catastro (ovc.catastro.meh.es) returns HTTP 403 to requests originating from
AWS / GCP / Azure datacenter ranges — the standard anti-scraping shield on
Spanish government APIs. We can still reach Catastro from EC2 by going
through the same Bright Data Scraping Browser session we already use for
Idealista, which routes outbound traffic through residential IPs.

This module exposes a single coroutine, `fetch_xml_via_brightdata`, that
the catastro.client module falls back to when the direct httpx call hits
the 403 / connection-blocked path. It uses Playwright's request context
attached to the Bright Data browser session rather than rendering a full
page — Playwright still sends the GET through the same proxy chain but
without paying the layout/parsing cost of an XML-as-HTML render.

Call sites in `catastro.client` wrap the response text in the existing XML
parser, so the proxy path is transparent to downstream consumers.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Allow Bright Data to spin up a fresh residential session. The first
# connect after an idle period is noticeably slower than steady-state.
CDP_CONNECT_TIMEOUT_MS = 25_000
REQUEST_TIMEOUT_MS = 25_000


def _brightdata_cdp_url() -> Optional[str]:
    """Read the Bright Data CDP WS URL fresh on every call so a missing env
    var at import time doesn't permanently disable the fallback path."""
    return os.getenv("BRIGHT_DATA_CDP")


async def fetch_xml_via_brightdata(url: str, params: dict[str, str]) -> str:
    """GET `url?<params>` through the Bright Data Scraping Browser and
    return the raw response body as text.

    Raises `httpx.HTTPError` on transport / HTTP failures so existing
    error-handling paths in catastro.client (which already catch
    `httpx.HTTPError`) work without modification.

    Raises `RuntimeError` when Bright Data is not configured — callers
    should treat that as "fallback unavailable, surface the original
    direct-fetch error".
    """
    cdp_url = _brightdata_cdp_url()
    if not cdp_url:
        raise RuntimeError(
            "BRIGHT_DATA_CDP is not configured; Catastro proxy fallback "
            "is unavailable"
        )

    logger.info("Catastro fallback: fetching %s via Bright Data", url)

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(
            cdp_url, timeout=CDP_CONNECT_TIMEOUT_MS
        )
        try:
            # A fresh context isolates cookies/storage so concurrent
            # Catastro lookups don't poison each other's session.
            context = await browser.new_context()
            try:
                response = await context.request.get(
                    url, params=params, timeout=REQUEST_TIMEOUT_MS
                )
                status = response.status
                body = await response.text()
                if status >= 400:
                    # Re-raise as httpx.HTTPStatusError so the upstream
                    # try/except in catastro.client picks it up the same
                    # way as a direct-fetch failure.
                    fake_request = httpx.Request("GET", url, params=params)
                    fake_response = httpx.Response(
                        status_code=status, request=fake_request, text=body
                    )
                    raise httpx.HTTPStatusError(
                        f"Catastro via Bright Data returned {status}",
                        request=fake_request,
                        response=fake_response,
                    )
                return body
            finally:
                await context.close()
        finally:
            await browser.close()
