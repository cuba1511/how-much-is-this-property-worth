"""
Idealista scraper using Bright Data's Scraping Browser (CDP over WebSocket).

The flow intentionally mirrors how a person would use the site:
1. Open idealista.com
2. Submit the real address in the search form
3. Apply filters on the listings page
4. Extract comparable listings from the final results page
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

from models import Listing

logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).with_name(".env"))

SBR_WS_CDP = os.getenv("BRIGHT_DATA_CDP")

IDEALISTA_BASE = "https://www.idealista.com"
IDEALISTA_HOME = f"{IDEALISTA_BASE}/"


def parse_price(text: str) -> Optional[int]:
    """Extract integer price from strings like '250.000 €' or '1.200.000€'."""
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def parse_m2(text: str) -> Optional[int]:
    """Extract m² value from strings like '80 m²' or '120m²'."""
    if not text:
        return None
    match = re.search(r"(\d+)\s*m", text)
    return int(match.group(1)) if match else None


def parse_rooms(text: str) -> Optional[int]:
    """Extract room count from strings like '3 hab.' or '2 habitaciones'."""
    if not text:
        return None
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else None


def compute_area_range(m2: Optional[int]) -> tuple[Optional[int], Optional[int]]:
    """Use a +/-20% area window to search for comparable properties."""
    if not m2:
        return None, None
    delta = max(10, int(round(m2 * 0.20)))
    return max(0, m2 - delta), m2 + delta


def rooms_filter_name(bedrooms: Optional[int]) -> Optional[str]:
    if bedrooms is None or bedrooms < 0:
        return None
    return "adfilter_rooms_4_more" if bedrooms >= 4 else f"adfilter_rooms_{bedrooms}"


def baths_filter_name(bathrooms: Optional[int]) -> Optional[str]:
    if bathrooms is None or bathrooms < 1:
        return None
    return "adfilter_baths_3" if bathrooms >= 3 else f"adfilter_baths_{bathrooms}"


async def wait_for_captcha_if_present(page) -> None:
    """Bright Data solves CAPTCHAs through a CDP command when needed."""
    try:
        client = await page.context.new_cdp_session(page)
        await client.send("Captcha.waitForSolve", {"detectTimeout": 30_000})
        logger.info("CAPTCHA handled by Bright Data")
    except Exception:
        logger.debug("No CAPTCHA challenge detected")


async def maybe_accept_cookies(page) -> None:
    """Dismiss the cookie banner when it appears."""
    selectors = (
        "#didomi-notice-agree-button",
        "button:has-text('Aceptar')",
        "button:has-text('Akzeptieren und fortfahren')",
        "button:has-text('Accept')",
    )
    for selector in selectors:
        try:
            button = page.locator(selector).first
            await button.wait_for(state="visible", timeout=2_000)
            await button.click()
            await page.wait_for_timeout(1_000)
            logger.info("Cookie banner accepted")
            return
        except Exception:
            continue


async def search_address(page, address: str) -> None:
    """Navigate from the homepage using Idealista's own search form."""
    await page.goto(IDEALISTA_HOME, wait_until="domcontentloaded", timeout=120_000)
    await wait_for_captcha_if_present(page)
    await maybe_accept_cookies(page)
    await page.wait_for_selector("#campoBus", timeout=30_000)
    await page.fill("#campoBus", address)
    await page.evaluate(
        """
        (searchText) => {
            const form = document.querySelector("#free-search-form");
            const input = document.querySelector("#campoBus");
            input.value = searchText;
            form.submit();
        }
        """,
        address,
    )
    await page.wait_for_load_state("domcontentloaded")
    await wait_for_captcha_if_present(page)


async def apply_filters(
    page,
    *,
    bedrooms: Optional[int],
    bathrooms: Optional[int],
    m2: Optional[int],
) -> None:
    """Apply comparable filters on Idealista's real filter form."""
    await page.wait_for_selector("#filter-form", timeout=30_000)
    area_min, area_max = compute_area_range(m2)
    await page.evaluate(
        """
        ({ areaMin, areaMax, roomFilterName, bathFilterName }) => {
            const form = document.querySelector("#filter-form");
            if (!form) {
                return;
            }

            const areaMinInput = form.querySelector('[name="adfilter_area"]');
            const areaMaxInput = form.querySelector('[name="adfilter_areamax"]');
            if (areaMinInput && areaMin != null) {
                areaMinInput.value = String(areaMin);
            }
            if (areaMaxInput && areaMax != null) {
                areaMaxInput.value = String(areaMax);
            }

            if (roomFilterName) {
                const roomInput = form.querySelector(`[name="${roomFilterName}"]`);
                if (roomInput) {
                    roomInput.checked = true;
                }
            }

            if (bathFilterName) {
                const bathInput = form.querySelector(`[name="${bathFilterName}"]`);
                if (bathInput) {
                    bathInput.checked = true;
                }
            }

            form.submit();
        }
        """,
        {
            "areaMin": area_min,
            "areaMax": area_max,
            "roomFilterName": rooms_filter_name(bedrooms),
            "bathFilterName": baths_filter_name(bathrooms),
        },
    )
    await page.wait_for_load_state("domcontentloaded")
    await wait_for_captcha_if_present(page)


async def extract_search_url(page) -> str:
    try:
        canonical = await page.locator("link[rel='canonical']").first.get_attribute("href")
        return canonical or page.url
    except Exception:
        return page.url


async def scrape_idealista_listings(
    address: str,
    bedrooms: Optional[int] = None,
    bathrooms: Optional[int] = None,
    m2: Optional[int] = None,
    max_listings: int = 30,
) -> tuple[list[Listing], str]:
    """
    Scrape Idealista listings using Bright Data's remote Chrome via CDP.

    Returns (listings, search_url).
    """
    listings: list[Listing] = []
    if not SBR_WS_CDP:
        raise ValueError("BRIGHT_DATA_CDP is not configured")

    logger.info(f"Connecting to Bright Data CDP: {SBR_WS_CDP[:60]}...")
    logger.info(f"Searching Idealista for address: {address}")

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(SBR_WS_CDP)
        page = await browser.new_page()

        try:
            await search_address(page, address)
            await apply_filters(page, bedrooms=bedrooms, bathrooms=bathrooms, m2=m2)
            search_url = await extract_search_url(page)
            logger.info(f"Final Idealista search URL: {search_url}")

            await page.wait_for_selector(
                "main#main-content, section.items-container, #h1-container__text",
                timeout=45_000,
            )
            await page.wait_for_timeout(2_000)

            raw_listings: list[dict] = await page.evaluate(
                """
                () => {
                    const articles = document.querySelectorAll(
                        'main#main-content section.items-container article.item, section.items-list article.item'
                    );

                    return Array.from(articles).map(article => {
                        const linkEl = article.querySelector('a.item-link');
                        const priceEl = article.querySelector('.item-price, .price-row .item-price');
                        const detailEls = article.querySelectorAll('.item-detail-char .item-detail');
                        const imgEl = article.querySelector('.item-gallery img, .item-multimedia img, .item-multimedia-pictures img');

                        const details = Array.from(detailEls).map(el => el.textContent.trim());
                        const title = linkEl?.getAttribute('title') || linkEl?.textContent?.trim() || null;

                        return {
                            url: linkEl ? linkEl.getAttribute('href') : null,
                            price: priceEl ? priceEl.textContent.trim() : null,
                            details: details,
                            address: title,
                            image: imgEl ? (imgEl.getAttribute('src') || imgEl.getAttribute('data-src')) : null,
                            title: title,
                        };
                    });
                }
                """
            )

            logger.info(f"Raw listings extracted: {len(raw_listings)}")

            for raw in raw_listings[:max_listings]:
                if not raw.get("url"):
                    continue

                price = parse_price(raw.get("price", ""))
                listing_m2 = None
                listing_beds = None
                listing_baths = None
                floor = None

                for detail in raw.get("details", []):
                    detail_lower = detail.lower()
                    if "m²" in detail_lower or "m2" in detail_lower:
                        listing_m2 = parse_m2(detail)
                    elif "hab" in detail_lower or "habitacion" in detail_lower:
                        listing_beds = parse_rooms(detail)
                    elif "baño" in detail_lower or "bano" in detail_lower:
                        listing_baths = parse_rooms(detail)
                    elif "planta" in detail_lower or "piso" in detail_lower:
                        floor = detail

                price_per_m2 = None
                if price and listing_m2 and listing_m2 > 0:
                    price_per_m2 = int(price / listing_m2)

                full_url = (
                    f"{IDEALISTA_BASE}{raw['url']}"
                    if raw["url"].startswith("/")
                    else raw["url"]
                )

                title = raw.get("title") or raw.get("address") or "Listing"

                listings.append(
                    Listing(
                        title=title,
                        price=price,
                        m2=listing_m2,
                        price_per_m2=price_per_m2,
                        bedrooms=listing_beds,
                        bathrooms=listing_baths,
                        address=raw.get("address"),
                        url=full_url,
                        image_url=raw.get("image"),
                        floor=floor,
                    )
                )

        except PlaywrightTimeout:
            search_url = page.url
            logger.warning(f"Timeout waiting for listings at {search_url}")
        except Exception as exc:
            logger.error(f"Scraping error: {exc}", exc_info=True)
            raise
        finally:
            await browser.close()

    logger.info(f"Parsed {len(listings)} listings successfully")
    return listings, search_url
