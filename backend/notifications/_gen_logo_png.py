"""One-off helper: rasterize the PropHero wordmark SVG to a retina PNG.

Email clients (Gmail/Outlook) do not render inline SVG, so the email header
needs a PNG. Run once to (re)generate ``assets/prophero-logo.png`` whenever the
source SVG changes:

    python -m notifications._gen_logo_png
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

ASSETS = Path(__file__).parent / "assets"
SVG_PATH = ASSETS / "prophero-logo.svg"
PNG_PATH = ASSETS / "prophero-logo.png"

# Source viewBox is 125x28; render at 2x for crisp retina display.
WIDTH, HEIGHT, SCALE = 125, 28, 4


async def main() -> None:
    svg = SVG_PATH.read_text(encoding="utf-8")
    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<style>html,body{margin:0;padding:0;background:transparent;}"
        f"#wrap{{width:{WIDTH}px;height:{HEIGHT}px;}}"
        f"#wrap svg{{width:{WIDTH}px;height:{HEIGHT}px;display:block;}}</style></head>"
        f"<body><div id='wrap'>{svg}</div></body></html>"
    )
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page(
                viewport={"width": WIDTH, "height": HEIGHT},
                device_scale_factor=SCALE,
            )
            await page.set_content(html, wait_until="domcontentloaded")
            element = await page.query_selector("#wrap")
            assert element is not None
            png = await element.screenshot(omit_background=True, type="png")
        finally:
            await browser.close()
    PNG_PATH.write_bytes(png)
    print(f"Wrote {PNG_PATH} ({len(png)} bytes) at {WIDTH*SCALE}x{HEIGHT*SCALE}")


if __name__ == "__main__":
    asyncio.run(main())
