"""HTML → PDF via Playwright (local Chromium).

We deliberately use a **local** Chromium launch — not the Bright Data CDP
endpoint that the scraper uses. The CDP browser is a paid scraping resource
and rendering our own HTML there would burn quota for no reason.

`playwright install chromium` (already in `make install`) is the only
prerequisite. The launch is async because FastAPI handlers are async; we
launch + close per call to keep memory predictable and to avoid stale state
across requests. For higher throughput we can swap to a long-lived browser
context later.
"""

from __future__ import annotations

import logging
from typing import Optional

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

DEFAULT_PDF_OPTIONS = {
    "format": "A4",
    "print_background": True,
    "margin": {
        "top": "0mm",
        "bottom": "0mm",
        "left": "0mm",
        "right": "0mm",
    },
}


async def generate_pdf_bytes(html: str, *, pdf_options: Optional[dict] = None) -> bytes:
    """Render `html` to a PDF byte string. Raises on failure."""
    options = {**DEFAULT_PDF_OPTIONS, **(pdf_options or {})}

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await page.set_content(html, wait_until="domcontentloaded")
            # Brief settle so any web fonts / async layout finishes before we snapshot.
            await page.wait_for_load_state("networkidle", timeout=5_000)
            pdf_bytes = await page.pdf(**options)
        finally:
            await browser.close()

    logger.info("PDF rendered, %d bytes", len(pdf_bytes))
    return pdf_bytes
