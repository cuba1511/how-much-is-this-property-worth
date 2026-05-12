"""
Idealista scraper using Bright Data's Scraping Browser (CDP over WebSocket).

The scraper now follows a staged comparable strategy:
1. Search the exact address
2. If there are too few comps, search the same street without the house number
3. If there are still too few comps, broaden to the municipality
4. Merge, de-duplicate, rank, and return the best comparables
"""

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import re
from urllib.parse import quote, urlsplit, urlunsplit
from statistics import median
from time import perf_counter
from typing import Optional

from dotenv import load_dotenv
from playwright.async_api import Page
from playwright.async_api import Route
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

from models import Listing, MunicipioInfo, SearchMetadata, SearchStageResult

logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).with_name(".env"))

SBR_WS_CDP = os.getenv("BRIGHT_DATA_CDP")

IDEALISTA_BASE = "https://www.idealista.com"
IDEALISTA_HOME = f"{IDEALISTA_BASE}/"
TARGET_COMPARABLES = 10
STOP_IF_COMPARABLES_REACHED = 8
STOP_IF_LOCAL_COMPARABLES_REACHED = 4
INITIAL_CAPTCHA_TIMEOUT_MS = 12_000
FOLLOW_UP_CAPTCHA_TIMEOUT_MS = 1_500
FILTER_CAPTCHA_TIMEOUT_MS = 750


@dataclass(frozen=True)
class SearchStageConfig:
    name: str
    label: str
    query: str
    stage_priority: int
    area_tolerance: float
    min_area_delta: int
    bedrooms_mode: str
    bathrooms_mode: str


@dataclass
class ComparableCandidate:
    listing: Listing
    stage_name: str
    stage_priority: int
    score: float


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


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
    """Extract room count from strings like '3 hab.' or '2 baños'."""
    if not text:
        return None
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else None


def compute_area_range(
    m2: Optional[int],
    *,
    tolerance: float,
    min_delta: int,
) -> tuple[Optional[int], Optional[int]]:
    """Build a dynamic area window for comparable properties."""
    if not m2:
        return None, None
    delta = max(min_delta, int(round(m2 * tolerance)))
    return max(0, m2 - delta), m2 + delta


def room_filter_bucket(rooms: int) -> str:
    if rooms <= 0:
        return "adfilter_rooms_0"
    if rooms >= 4:
        return "adfilter_rooms_4_more"
    return f"adfilter_rooms_{rooms}"


def bath_filter_bucket(bathrooms: int) -> str:
    if bathrooms >= 3:
        return "adfilter_baths_3"
    return f"adfilter_baths_{max(1, bathrooms)}"


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def room_filter_names(bedrooms: Optional[int], mode: str) -> list[str]:
    if bedrooms is None or bedrooms < 0 or mode == "any":
        return []
    if mode == "exact":
        return [room_filter_bucket(bedrooms)]
    if mode == "plus_minus_one":
        return unique_preserve_order(
            [
                room_filter_bucket(max(0, bedrooms - 1)),
                room_filter_bucket(bedrooms),
                room_filter_bucket(bedrooms + 1),
            ]
        )
    return []


def bath_filter_names(bathrooms: Optional[int], mode: str) -> list[str]:
    if bathrooms is None or bathrooms < 1 or mode == "any":
        return []
    if mode == "exact":
        return [bath_filter_bucket(bathrooms)]
    if mode == "at_least_minus_one":
        start = max(1, bathrooms - 1)
        if start == 1:
            return ["adfilter_baths_1", "adfilter_baths_2", "adfilter_baths_3"]
        if start == 2:
            return ["adfilter_baths_2", "adfilter_baths_3"]
        return ["adfilter_baths_3"]
    return []


def strip_street_number(address: str) -> str:
    parts = [normalize_space(part) for part in address.split(",") if normalize_space(part)]
    if not parts:
        return normalize_space(address)

    street = re.sub(r"\s+\d+[A-Za-z0-9/-]*\s*$", "", parts[0]).strip(" ,")
    if len(parts) > 1 and re.fullmatch(r"\d+[A-Za-z0-9/-]*", parts[1]):
        parts = [street or parts[0], *parts[2:]]
    else:
        parts = [street or parts[0], *parts[1:]]

    return normalize_space(", ".join(part for part in parts if part))


def build_same_street_query(address: str, municipio: MunicipioInfo) -> str:
    road = normalize_space(municipio.road or "")
    municipality = normalize_space(municipio.name)
    if road and municipality:
        return f"{road}, {municipality}"
    if road:
        return road
    return strip_street_number(address)


def build_broader_zone_query(address: str, municipio: MunicipioInfo) -> str:
    locality_candidates = [
        municipio.quarter,
        municipio.neighbourhood,
        municipio.city_district,
        municipio.name,
    ]
    locality = next((normalize_space(value) for value in locality_candidates if normalize_space(value or "")), "")
    municipality = normalize_space(municipio.name)

    if locality and municipality and locality.lower() != municipality.lower():
        return f"{locality}, {municipality}"
    if locality:
        return locality
    return municipality or normalize_space(address)


def build_search_stages(address: str, municipio: MunicipioInfo) -> list[SearchStageConfig]:
    exact_query = normalize_space(address)
    street_query = build_same_street_query(address, municipio)
    broader_query = build_broader_zone_query(address, municipio)

    stages = [
        SearchStageConfig(
            name="exact_address",
            label="Direccion exacta",
            query=exact_query,
            stage_priority=0,
            area_tolerance=0.20,
            min_area_delta=10,
            bedrooms_mode="exact",
            bathrooms_mode="exact",
        ),
        SearchStageConfig(
            name="same_street",
            label="Misma calle",
            query=street_query,
            stage_priority=1,
            area_tolerance=0.30,
            min_area_delta=15,
            bedrooms_mode="exact",
            bathrooms_mode="at_least_minus_one",
        ),
        SearchStageConfig(
            name="broader_zone",
            label="Zona amplia",
            query=broader_query,
            stage_priority=2,
            area_tolerance=0.40,
            min_area_delta=20,
            bedrooms_mode="plus_minus_one",
            bathrooms_mode="at_least_minus_one",
        ),
    ]

    deduped: list[SearchStageConfig] = []
    seen_queries: set[str] = set()
    for stage in stages:
        normalized_query = normalize_space(stage.query).lower()
        if not normalized_query or normalized_query in seen_queries:
            continue
        seen_queries.add(normalized_query)
        deduped.append(stage)
    return deduped


def build_listing_from_raw(raw: dict, source_stage: str) -> Optional[Listing]:
    if not raw.get("url"):
        return None

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

    return Listing(
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
        source_stage=source_stage,
    )


def canonical_listing_url(url: str) -> str:
    split = urlsplit(url)
    return urlunsplit((split.scheme, split.netloc, split.path, "", ""))


def build_direct_search_url(query: str) -> str:
    encoded_query = quote(query.replace(" ", "_"), safe=",_-")
    return f"{IDEALISTA_BASE}/buscar/venta-viviendas/{encoded_query}/"


def score_listing(
    listing: Listing,
    *,
    target_m2: Optional[int],
    target_bedrooms: Optional[int],
    target_bathrooms: Optional[int],
    stage_priority: int,
) -> float:
    area_penalty = 20.0
    if listing.m2 and target_m2:
        area_penalty = abs(listing.m2 - target_m2) / max(target_m2, 1) * 100

    bedroom_penalty = 6.0
    if listing.bedrooms is not None and target_bedrooms is not None:
        bedroom_penalty = abs(listing.bedrooms - target_bedrooms) * 12

    bathroom_penalty = 4.0
    if listing.bathrooms is not None and target_bathrooms is not None:
        bathroom_penalty = abs(listing.bathrooms - target_bathrooms) * 10

    return stage_priority * 40 + area_penalty + bedroom_penalty + bathroom_penalty


def dedupe_candidates(candidates: list[ComparableCandidate]) -> list[ComparableCandidate]:
    best_by_url: dict[str, ComparableCandidate] = {}
    for candidate in candidates:
        normalized_url = canonical_listing_url(candidate.listing.url)
        previous = best_by_url.get(normalized_url)
        if previous is None or candidate.score < previous.score:
            if normalized_url != candidate.listing.url:
                candidate.listing.url = normalized_url
            best_by_url[normalized_url] = candidate
    return list(best_by_url.values())


def filter_price_outliers(candidates: list[ComparableCandidate]) -> list[ComparableCandidate]:
    ppms = [
        candidate.listing.price_per_m2
        for candidate in candidates
        if candidate.listing.price_per_m2
    ]
    if len(ppms) < 5:
        return candidates

    ppm_median = median(ppms)
    filtered = [
        candidate
        for candidate in candidates
        if candidate.listing.price_per_m2 is None
        or (ppm_median * 0.55) <= candidate.listing.price_per_m2 <= (ppm_median * 1.80)
    ]
    return filtered if len(filtered) >= max(3, len(candidates) // 2) else candidates


def rank_candidates(
    candidates: list[ComparableCandidate],
    *,
    max_listings: int,
) -> list[Listing]:
    deduped = dedupe_candidates(candidates)
    filtered = filter_price_outliers(deduped)
    ranked = sorted(filtered, key=lambda candidate: (candidate.score, candidate.listing.price or 0))
    return [candidate.listing for candidate in ranked[:max_listings]]


def should_stop_after_stage(stage: SearchStageConfig, ranked_listings: list[Listing]) -> bool:
    if len(ranked_listings) >= STOP_IF_COMPARABLES_REACHED:
        return True
    if stage.name == "same_street" and len(ranked_listings) >= STOP_IF_LOCAL_COMPARABLES_REACHED:
        return True
    return False


async def block_nonessential_resources(route: Route) -> None:
    if route.request.resource_type in {"image", "media", "font"}:
        await route.abort()
        return
    await route.continue_()


async def wait_for_captcha_if_present(page: Page, detect_timeout_ms: int) -> int:
    """Bright Data solves CAPTCHAs through a CDP command when needed."""
    started_at = perf_counter()
    try:
        client = await page.context.new_cdp_session(page)
        await client.send("Captcha.waitForSolve", {"detectTimeout": detect_timeout_ms})
        duration_ms = int((perf_counter() - started_at) * 1000)
        logger.info(f"CAPTCHA check finished in {duration_ms}ms")
        return duration_ms
    except Exception:
        return int((perf_counter() - started_at) * 1000)


async def maybe_accept_cookies(page: Page) -> None:
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
            await button.wait_for(state="visible", timeout=750)
            await button.click()
            logger.info("Cookie banner accepted")
            return
        except Exception:
            continue


async def search_address(
    page: Page,
    query: str,
    *,
    detect_timeout_ms: int,
) -> None:
    """Search a location using a direct Idealista search URL."""
    query = normalize_space(query)
    await page.goto(build_direct_search_url(query), wait_until="commit", timeout=45_000)
    await maybe_accept_cookies(page)
    await page.wait_for_selector(
        "#filter-form, #h1-container__text, section.items-list, main#main-content",
        timeout=15_000,
    )
    await wait_for_captcha_if_present(page, detect_timeout_ms)


async def apply_filters(
    page: Page,
    *,
    room_filters: list[str],
    bath_filters: list[str],
    area_min: Optional[int],
    area_max: Optional[int],
    captcha_timeout_ms: int,
) -> None:
    """Apply comparable filters on Idealista's real filter form."""
    await page.wait_for_selector("#filter-form", timeout=20_000)
    await page.evaluate(
        """
        ({ areaMin, areaMax, roomFilters, bathFilters }) => {
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

            roomFilters.forEach((filterName) => {
                const roomInput = form.querySelector(`[name="${filterName}"]`);
                if (roomInput) {
                    roomInput.checked = true;
                }
            });

            bathFilters.forEach((filterName) => {
                const bathInput = form.querySelector(`[name="${filterName}"]`);
                if (bathInput) {
                    bathInput.checked = true;
                }
            });

            form.submit();
        }
        """,
        {
            "areaMin": area_min,
            "areaMax": area_max,
            "roomFilters": room_filters,
            "bathFilters": bath_filters,
        },
    )
    await page.wait_for_selector(
        "#h1-container__text, main#main-content section.items-container, section.items-list",
        timeout=15_000,
    )
    await wait_for_captcha_if_present(page, captcha_timeout_ms)


async def wait_for_results(page: Page) -> None:
    await page.wait_for_selector(
        "#h1-container__text, main#main-content section.items-container, section.items-list",
        timeout=15_000,
    )


async def extract_search_url(page: Page) -> str:
    try:
        canonical = await page.locator("link[rel='canonical']").first.get_attribute("href")
        return canonical or page.url
    except Exception:
        return page.url


async def extract_raw_listings(page: Page) -> list[dict]:
    return await page.evaluate(
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


async def run_search_stage(
    page: Page,
    stage: SearchStageConfig,
    *,
    target_m2: Optional[int],
    target_bedrooms: Optional[int],
    target_bathrooms: Optional[int],
    max_listings: int,
) -> tuple[list[Listing], SearchStageResult]:
    stage_started_at = perf_counter()

    area_min, area_max = compute_area_range(
        target_m2,
        tolerance=stage.area_tolerance,
        min_delta=stage.min_area_delta,
    )
    room_filters = room_filter_names(target_bedrooms, stage.bedrooms_mode)
    bath_filters = bath_filter_names(target_bathrooms, stage.bathrooms_mode)
    search_captcha_timeout_ms = (
        INITIAL_CAPTCHA_TIMEOUT_MS
        if stage.stage_priority == 0
        else FOLLOW_UP_CAPTCHA_TIMEOUT_MS
    )

    try:
        await search_address(
            page,
            stage.query,
            detect_timeout_ms=search_captcha_timeout_ms,
        )
        await apply_filters(
            page,
            room_filters=room_filters,
            bath_filters=bath_filters,
            area_min=area_min,
            area_max=area_max,
            captcha_timeout_ms=FILTER_CAPTCHA_TIMEOUT_MS,
        )
        await wait_for_results(page)
        search_url = await extract_search_url(page)
        raw_listings = await extract_raw_listings(page)
        listings = [
            listing
            for raw in raw_listings[: max_listings * 2]
            if (listing := build_listing_from_raw(raw, stage.name))
        ]
        duration_ms = int((perf_counter() - stage_started_at) * 1000)
        logger.info(
            f"Stage {stage.name} finished in {duration_ms}ms with {len(listings)} listings"
        )
        return (
            listings,
            SearchStageResult(
                name=stage.name,
                label=stage.label,
                query=stage.query,
                search_url=search_url,
                listings_found=len(listings),
                duration_ms=duration_ms,
                area_min=area_min,
                area_max=area_max,
                bedrooms_mode=stage.bedrooms_mode,
                bathrooms_mode=stage.bathrooms_mode,
            ),
        )
    except PlaywrightTimeout:
        duration_ms = int((perf_counter() - stage_started_at) * 1000)
        search_url = await extract_search_url(page)
        logger.warning(f"Stage {stage.name} timed out at {search_url}")
        return (
            [],
            SearchStageResult(
                name=stage.name,
                label=stage.label,
                query=stage.query,
                search_url=search_url,
                listings_found=0,
                duration_ms=duration_ms,
                area_min=area_min,
                area_max=area_max,
                bedrooms_mode=stage.bedrooms_mode,
                bathrooms_mode=stage.bathrooms_mode,
            ),
        )
def build_candidates(
    listings: list[Listing],
    *,
    stage_name: str,
    stage_priority: int,
    target_m2: Optional[int],
    target_bedrooms: Optional[int],
    target_bathrooms: Optional[int],
) -> list[ComparableCandidate]:
    return [
        ComparableCandidate(
            listing=listing,
            stage_name=stage_name,
            stage_priority=stage_priority,
            score=score_listing(
                listing,
                target_m2=target_m2,
                target_bedrooms=target_bedrooms,
                target_bathrooms=target_bathrooms,
                stage_priority=stage_priority,
            ),
        )
        for listing in listings
    ]


async def scrape_idealista_listings(
    address: str,
    *,
    municipio: MunicipioInfo,
    bedrooms: Optional[int] = None,
    bathrooms: Optional[int] = None,
    m2: Optional[int] = None,
    max_listings: int = 15,
) -> tuple[list[Listing], str, SearchMetadata]:
    """
    Scrape Idealista listings using Bright Data's remote Chrome via CDP.

    Returns (ranked_listings, final_search_url, search_metadata).
    """
    if not SBR_WS_CDP:
        raise ValueError("BRIGHT_DATA_CDP is not configured")

    total_started_at = perf_counter()
    stages = build_search_stages(address, municipio)
    candidates: list[ComparableCandidate] = []
    executed_stages: list[SearchStageResult] = []
    final_search_url = IDEALISTA_HOME

    logger.info(f"Connecting to Bright Data CDP: {SBR_WS_CDP[:60]}...")
    connect_started_at = perf_counter()

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(SBR_WS_CDP)
        logger.info(
            f"Connected to Bright Data CDP in {int((perf_counter() - connect_started_at) * 1000)}ms"
        )
        page = await browser.new_page()
        await page.route("**/*", block_nonessential_resources)

        try:
            for stage in stages:
                listings, stage_result = await run_search_stage(
                    page,
                    stage,
                    target_m2=m2,
                    target_bedrooms=bedrooms,
                    target_bathrooms=bathrooms,
                    max_listings=max_listings,
                )
                executed_stages.append(stage_result)
                final_search_url = stage_result.search_url
                candidates.extend(
                    build_candidates(
                        listings,
                        stage_name=stage.name,
                        stage_priority=stage.stage_priority,
                        target_m2=m2,
                        target_bedrooms=bedrooms,
                        target_bathrooms=bathrooms,
                    )
                )

                ranked_so_far = rank_candidates(candidates, max_listings=max_listings)
                if should_stop_after_stage(stage, ranked_so_far):
                    break
        finally:
            await browser.close()

    ranked_listings = rank_candidates(candidates, max_listings=max_listings)
    total_duration_ms = int((perf_counter() - total_started_at) * 1000)
    final_stage = executed_stages[-1].name if executed_stages else "none"

    search_metadata = SearchMetadata(
        strategy="hybrid_fallback",
        target_comparables=TARGET_COMPARABLES,
        final_stage=final_stage,
        total_duration_ms=total_duration_ms,
        stages=executed_stages,
    )

    logger.info(
        f"Parsed {len(ranked_listings)} ranked listings across {len(executed_stages)} stages in {total_duration_ms}ms"
    )
    return ranked_listings, final_search_url, search_metadata
