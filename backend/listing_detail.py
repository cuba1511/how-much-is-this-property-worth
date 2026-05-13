"""
Listing detail enrichment.

Idealista's SERP does not expose bathrooms (and rarely exposes amenities such
as pool/garden/terrace/AC/condition). To get a reliable signal for those
fields we open the individual listing page after ranking is done, in parallel
with a small concurrency budget, and merge the structured features back into
the SERP-derived Listing.
"""

import asyncio
import logging
import re
from time import perf_counter
from typing import Optional

from playwright.async_api import Browser
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeout

from models import Listing
from scraper import (
    AC_KEYWORDS,
    CONDITION_MAP,
    NO_ELEVATOR_PHRASES,
    block_nonessential_resources,
    normalize_space,
    parse_rooms,
    strip_accents,
    wait_for_captcha_if_present,
)

logger = logging.getLogger(__name__)


DETAIL_WAIT_SELECTOR = (
    ".details-property-feature-one, "
    ".details-property_features, "
    "#details, "
    "section.detail-info, "
    "main"
)
DETAIL_CAPTCHA_TIMEOUT_MS = 1_500

DETAIL_EXTRACT_JS = """
() => {
    const text = (el) => (el?.textContent || '').replace(/\\s+/g, ' ').trim();
    const all = (sel) => Array.from(document.querySelectorAll(sel))
        .map(text)
        .filter(Boolean);

    const basicFeatures = all(
        '.details-property-feature-one ul li, .details-property_features ul li'
    );
    const equipment = all('.details-property-feature-two ul li');
    const description = text(
        document.querySelector('.comment .adCommentsLanguage, #freeTextContainer, .comment p')
    );
    const conditionLabel = text(
        document.querySelector(
            '.details-property-feature-one .txt-secondary-medium, [data-testid="condition"]'
        )
    );
    const bodyFallback = (document.body?.innerText || '').slice(0, 4000);

    return { basicFeatures, equipment, description, conditionLabel, bodyFallback };
}
"""


BATHROOM_REGEX = re.compile(
    r"(\d+)\s*(banos?|aseos?|wc|bath)",
    re.IGNORECASE,
)


def _extract_bathrooms(
    basic_features: list[str],
    equipment: list[str],
    body_fallback: str,
) -> Optional[int]:
    """Find the bathroom count first in structured features, then in body text."""
    for feature in [*basic_features, *equipment]:
        feature_ascii = strip_accents(feature.lower())
        if "bano" in feature_ascii or "aseo" in feature_ascii or " wc" in feature_ascii:
            count = parse_rooms(feature)
            if count is not None:
                return count

    body_ascii = strip_accents(body_fallback.lower())
    match = BATHROOM_REGEX.search(body_ascii)
    if match:
        return int(match.group(1))
    return None


def _detect_condition(
    basic_features: list[str],
    condition_label: Optional[str],
) -> Optional[str]:
    """Map a free-form 'condition' string to the same buckets used in the SERP."""
    candidates: list[str] = []
    if condition_label:
        candidates.append(condition_label)
    candidates.extend(basic_features)

    for candidate in candidates:
        candidate_lower = normalize_space(candidate).lower()
        for key, value in CONDITION_MAP.items():
            if key in candidate_lower:
                return value
    return None


def _features_text(
    basic_features: list[str],
    equipment: list[str],
    description: Optional[str],
) -> str:
    parts = [*(basic_features or []), *(equipment or [])]
    if description:
        parts.append(description)
    return strip_accents(" \n ".join(parts).lower())


def _has_keyword(text_ascii: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword.strip() in text_ascii for keyword in keywords)


def _build_detail_signals(detail: dict) -> dict:
    """Convert raw extracted detail data into the same shape parse_listing_signals returns."""
    basic_features: list[str] = detail.get("basicFeatures") or []
    equipment: list[str] = detail.get("equipment") or []
    description: Optional[str] = detail.get("description") or None
    condition_label: Optional[str] = detail.get("conditionLabel") or None
    body_fallback: str = detail.get("bodyFallback") or ""

    text_ascii = _features_text(basic_features, equipment, description)

    bathrooms = _extract_bathrooms(basic_features, equipment, body_fallback)
    condition = _detect_condition(basic_features, condition_label)

    has_elevator: Optional[bool] = None
    if text_ascii:
        if any(strip_accents(phrase) in text_ascii for phrase in NO_ELEVATOR_PHRASES):
            has_elevator = False
        elif "con ascensor" in text_ascii or "ascensor" in text_ascii:
            has_elevator = True

    has_terrace = True if "terraza" in text_ascii else None
    has_pool = True if "piscina" in text_ascii else None
    has_garden = True if ("jardin" in text_ascii or "zonas verdes" in text_ascii) else None
    has_storage_room = True if "trastero" in text_ascii else None
    has_garage: Optional[bool] = None
    if (
        "garaje" in text_ascii
        or "parking" in text_ascii
        or "plaza de garaje" in text_ascii
    ):
        has_garage = True

    has_ac: Optional[bool] = None
    if _has_keyword(text_ascii, AC_KEYWORDS):
        has_ac = True

    return {
        "bathrooms": bathrooms,
        "condition": condition,
        "has_elevator": has_elevator,
        "has_terrace": has_terrace,
        "has_pool": has_pool,
        "has_garage": has_garage,
        "has_garden": has_garden,
        "has_storage_room": has_storage_room,
        "has_air_conditioning": has_ac,
        "description": description,
        "basic_features": basic_features,
        "equipment": equipment,
    }


def _merge_listing_with_detail(listing: Listing, signals: dict) -> Listing:
    """Apply detail-derived data to a Listing without clobbering positive SERP signals."""
    bathrooms = signals.get("bathrooms")
    if bathrooms is not None:
        listing.bathrooms = bathrooms

    # Only fill the booleans/condition when the SERP gave us None.
    optional_fields = (
        "condition",
        "has_elevator",
        "has_terrace",
        "has_pool",
        "has_garage",
        "has_garden",
        "has_storage_room",
        "has_air_conditioning",
    )
    for field in optional_fields:
        current = getattr(listing, field)
        new_value = signals.get(field)
        if current is None and new_value is not None:
            setattr(listing, field, new_value)

    # Merge features into tags (preserve order, drop duplicates).
    extra_tags = [
        normalize_space(value).lower()
        for value in (signals.get("basic_features") or []) + (signals.get("equipment") or [])
        if value
    ]
    if extra_tags:
        seen = {tag for tag in listing.tags}
        for tag in extra_tags:
            if tag and tag not in seen:
                listing.tags.append(tag)
                seen.add(tag)

    return listing


async def _enrich_single_listing(
    browser: Browser,
    listing: Listing,
    *,
    semaphore: asyncio.Semaphore,
    per_listing_timeout_ms: int,
) -> Listing:
    """Open one detail page, extract structured signals and merge into the Listing.

    Idealista detail pages can be slow to render and may hide content behind a
    CAPTCHA wall, so we keep waits short and best-effort: we always try to
    evaluate the extraction script, even when the selector wait fails. Even a
    partially-loaded ``document.body.innerText`` is enough to recover the
    bathroom count via regex.
    """
    started_at = perf_counter()
    async with semaphore:
        page: Optional[Page] = None
        try:
            page = await browser.new_page()
            await page.route("**/*", block_nonessential_resources)
            goto_budget_ms = max(8_000, int(per_listing_timeout_ms * 0.6))
            await page.goto(
                listing.url,
                wait_until="domcontentloaded",
                timeout=goto_budget_ms,
            )
            await wait_for_captcha_if_present(page, DETAIL_CAPTCHA_TIMEOUT_MS)
            try:
                await page.wait_for_selector(
                    DETAIL_WAIT_SELECTOR,
                    timeout=max(2_000, int(per_listing_timeout_ms * 0.25)),
                    state="attached",
                )
            except PlaywrightTimeout:
                logger.info(
                    "Detail enrichment selector wait timed out for %s; evaluating anyway",
                    listing.url,
                )
            detail = await page.evaluate(DETAIL_EXTRACT_JS)
            signals = _build_detail_signals(detail)
            _merge_listing_with_detail(listing, signals)
            duration_ms = int((perf_counter() - started_at) * 1000)
            logger.info(
                "Detail enrichment for %s: bathrooms=%s features=%s took=%dms",
                listing.url,
                signals.get("bathrooms"),
                (signals.get("basic_features") or [])[:6],
                duration_ms,
            )
        except PlaywrightTimeout:
            logger.warning(
                "Detail enrichment timed out for %s after %dms",
                listing.url,
                int((perf_counter() - started_at) * 1000),
            )
        except PlaywrightError as exc:
            logger.warning("Detail enrichment failed for %s: %s", listing.url, exc)
        except Exception as exc:  # noqa: BLE001 - protect the whole pipeline
            logger.warning(
                "Detail enrichment unexpected error for %s: %s",
                listing.url,
                exc,
            )
        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception:  # noqa: BLE001 - closing must never raise
                    pass
    return listing


async def enrich_listings_with_details(
    browser: Browser,
    listings: list[Listing],
    *,
    max_concurrent: int = 10,
    per_listing_timeout_ms: int = 15_000,
) -> list[Listing]:
    """Open each top-N listing detail page in parallel and merge structured signals."""
    if not listings:
        return listings

    started_at = perf_counter()
    semaphore = asyncio.Semaphore(max_concurrent)
    tasks = [
        _enrich_single_listing(
            browser,
            listing,
            semaphore=semaphore,
            per_listing_timeout_ms=per_listing_timeout_ms,
        )
        for listing in listings
    ]
    enriched = await asyncio.gather(*tasks, return_exceptions=False)
    total_ms = int((perf_counter() - started_at) * 1000)
    with_baths = sum(1 for listing in enriched if listing.bathrooms is not None)
    logger.info(
        "Detail enrichment finished: %d/%d listings have bathrooms in %dms",
        with_baths,
        len(enriched),
        total_ms,
    )
    return enriched
