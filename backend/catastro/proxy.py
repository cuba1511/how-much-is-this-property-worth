"""Bright Data fallback for Catastro requests.

Catastro (ovc.catastro.meh.es) returns HTTP 403 to requests originating
from AWS / GCP / Azure datacenter ranges — the standard anti-scraping
shield on Spanish government APIs. We can still reach Catastro from EC2
by going through the same Bright Data Scraping Browser session we use
for Idealista, which routes outbound traffic through residential IPs
and presents a real-browser TLS / JS fingerprint.

This module exposes a single coroutine, `fetch_xml_via_brightdata`, that
the catastro.client module falls back to when the direct httpx call hits
the 403 / connection-blocked path. We drive a full page navigation
(`page.goto`) rather than a bare request because the Scraping Browser's
anti-bot capabilities (TLS fingerprint, JS challenges, header
synthesis) only kick in for browser navigations — bare HTTP requests
through the same channel still get 403'd by Catastro.

Call sites in `catastro.client` wrap the response text in the existing
XML parser, so the proxy path is transparent to downstream consumers.
"""

from __future__ import annotations

import logging
import os
import urllib.parse
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
NAVIGATION_TIMEOUT_MS = 25_000


def _brightdata_cdp_url() -> Optional[str]:
    """Read the Bright Data CDP WS URL fresh on every call so a missing env
    var at import time doesn't permanently disable the fallback path."""
    return os.getenv("BRIGHT_DATA_CDP")


def _extract_xml(rendered_text: str) -> str:
    """Strip the HTML wrapper Chromium adds around XML documents.

    When Chromium navigates to an XML response, it renders the document as
    a coloured tree under <html><body>. The raw XML survives intact as the
    body innerText (or innerHTML of the formatted view), so we drop the
    `<?xml-stylesheet ...?>` block if present and start from the first
    `<?xml` declaration."""
    text = rendered_text.strip()
    xml_decl = text.find("<?xml")
    if xml_decl > 0:
        text = text[xml_decl:]
    return text


async def fetch_xml_via_brightdata(url: str, params: dict[str, str]) -> str:
    """Navigate to `url?<params>` through the Bright Data Scraping Browser
    and return the raw XML body as text.

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

    qs = urllib.parse.urlencode(params, doseq=False)
    full_url = f"{url}?{qs}" if qs else url
    logger.info("Catastro fallback: navigating to %s via Bright Data", url)

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(
            cdp_url, timeout=CDP_CONNECT_TIMEOUT_MS
        )
        try:
            # A fresh context isolates cookies/storage so concurrent
            # Catastro lookups don't poison each other's session.
            context = await browser.new_context()
            try:
                page = await context.new_page()
                response = await page.goto(
                    full_url,
                    wait_until="domcontentloaded",
                    timeout=NAVIGATION_TIMEOUT_MS,
                )
                if response is None:
                    fake_request = httpx.Request("GET", full_url)
                    raise httpx.RequestError(
                        "Catastro via Bright Data: no response object",
                        request=fake_request,
                    )

                status = response.status
                if status >= 400:
                    body_preview = (await response.text())[:300]
                    fake_request = httpx.Request("GET", full_url)
                    fake_response = httpx.Response(
                        status_code=status,
                        request=fake_request,
                        text=body_preview,
                    )
                    raise httpx.HTTPStatusError(
                        f"Catastro via Bright Data returned {status}",
                        request=fake_request,
                        response=fake_response,
                    )

                # `response.text()` returns the raw HTTP body — for an XML
                # document that's the unparsed XML, exactly what we want.
                # If Catastro ever decides to serve HTML (error page, etc.)
                # we fall back to the rendered text and try to recover the
                # XML from it via `_extract_xml`.
                raw_body = await response.text()
                if raw_body.lstrip().startswith("<?xml"):
                    return raw_body

                rendered = await page.evaluate(
                    "() => document.documentElement.innerText"
                )
                return _extract_xml(rendered)
            finally:
                await context.close()
        finally:
            await browser.close()
