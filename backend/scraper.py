"""
Idealista scraper using Bright Data's Scraping Browser (CDP over WebSocket).

Comparable collection follows layered geography:
1. Same street
2. Same microzone
3. Same district
4. Municipality
"""

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import re
import unicodedata
from urllib.parse import quote, urlsplit, urlunsplit
from statistics import median
from time import perf_counter
from typing import Optional

from dotenv import load_dotenv
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from playwright.async_api import Route
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

from models import Listing, MunicipioInfo, SearchMetadata, SearchStageResult

logger = logging.getLogger(__name__)

# Imported lazily inside scrape_idealista_listings to avoid an import cycle
# (listing_detail imports helpers from this module).

load_dotenv(Path(__file__).with_name(".env"))

SBR_WS_CDP = os.getenv("BRIGHT_DATA_CDP")

IDEALISTA_BASE = "https://www.idealista.com"
IDEALISTA_HOME = f"{IDEALISTA_BASE}/"
TARGET_COMPARABLES = 10
STOP_RULES_BY_STAGE = {
    "same_street": 3,
    "same_microzone": 5,
    "same_local_area": 8,
    "municipality": 8,
}
INITIAL_CAPTCHA_TIMEOUT_MS = 12_000
FOLLOW_UP_CAPTCHA_TIMEOUT_MS = 1_500
FILTER_CAPTCHA_TIMEOUT_MS = 750

CONDITION_MAP = {
    "obra nueva": "obra_nueva",
    "promocion": "obra_nueva",
    "promociones": "obra_nueva",
    "promocion de obra nueva": "obra_nueva",
    "reformado": "reformado",
    "reformada": "reformado",
    "a reformar": "a_reformar",
    "para reformar": "a_reformar",
    "segunda mano": "segunda_mano",
    "de segunda mano": "segunda_mano",
    "segunda mano/buen estado": "segunda_mano",
    "segunda mano/para reformar": "a_reformar",
}

AC_KEYWORDS = (
    "aire acondicionado",
    "climatizacion",
    "climatización",
    "climatizado",
    "climatizada",
    " a/a ",
    " a.a ",
    " aa ",
)

NO_ELEVATOR_PHRASES = (
    "sin ascensor",
    "no ascensor",
    "no tiene ascensor",
    "no dispone de ascensor",
    "sin elevador",
)

# Idealista's SERP does not expose bathrooms as a structured detail, but the
# truncated description often mentions them ("3 dormitorios y 2 baños",
# "2 cuartos de baño", "1 aseo"). This regex covers the common forms so the
# scraper can keep a bathrooms signal even when detail enrichment fails.
BATHROOM_DESCRIPTION_REGEX = re.compile(
    r"(\d+)\s+(?:cuartos?\s+de\s+)?(?:banos?|aseos?|wc)\b",
    re.IGNORECASE,
)


def extract_bathrooms_from_description(description: Optional[str]) -> Optional[int]:
    """Best-effort regex extraction of bathroom count from a free-form description."""
    if not description:
        return None
    description_ascii = strip_accents(description.lower())
    match = BATHROOM_DESCRIPTION_REGEX.search(description_ascii)
    return int(match.group(1)) if match else None


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


def strip_accents(text: str) -> str:
    """Remove combining accents so 'baños', 'banos' and 'baÃ±os' all collapse to 'banos'."""
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", text or "")
        if not unicodedata.combining(char)
    )


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


FLOOR_WORD_MAP: dict[str, Optional[int]] = {
    "sotano": -1,
    "sótano": -1,
    "subterraneo": -1,
    "subterráneo": -1,
    "semisotano": -1,
    "semisótano": -1,
    "bajo": 0,
    "entresuelo": 0,
    "entreplanta": 0,
    "principal": 1,
    "atico": None,
    "ático": None,
}


def parse_floor_number(floor_text: Optional[str]) -> Optional[int]:
    """Convert a free-form floor string ('Bajo', '3ª planta', 'Planta 5') to an int."""
    if not floor_text:
        return None
    text = floor_text.strip().lower()
    if not text:
        return None
    for word, value in FLOOR_WORD_MAP.items():
        if word in text:
            return value
    match = re.search(r"(\d+)\s*[ªa\.]*\s*planta", text)
    if not match:
        match = re.search(r"planta\s*(\d+)", text)
    if not match:
        match = re.search(r"\b(\d+)\b", text)
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


def build_microzone_query(municipio: MunicipioInfo) -> str:
    microzone_candidates = [
        municipio.quarter,
        municipio.neighbourhood,
    ]
    microzone = next(
        (normalize_space(value) for value in microzone_candidates if normalize_space(value or "")),
        "",
    )
    municipality = normalize_space(municipio.name)

    if microzone and municipality and microzone.lower() != municipality.lower():
        return f"{microzone}, {municipality}"
    return microzone or municipality


def build_district_query(municipio: MunicipioInfo) -> str:
    district = normalize_space(municipio.city_district or "")
    municipality = normalize_space(municipio.name)

    if district and municipality and district.lower() != municipality.lower():
        return f"{district}, {municipality}"
    return district or municipality


def build_municipality_query(municipio: MunicipioInfo) -> str:
    municipality = normalize_space(municipio.name)
    province = normalize_space(municipio.province or "")
    if municipality and province and municipality.lower() != province.lower():
        return f"{municipality}, {province}"
    return municipality


def build_search_stages(address: str, municipio: MunicipioInfo) -> list[SearchStageConfig]:
    street_query = build_same_street_query(address, municipio)
    microzone_query = build_microzone_query(municipio)
    district_query = build_district_query(municipio)
    municipality_query = build_municipality_query(municipio)

    stages = [
        SearchStageConfig(
            name="same_street",
            label="Misma calle",
            query=street_query,
            stage_priority=0,
            area_tolerance=0.25,
            min_area_delta=12,
            bedrooms_mode="exact",
            bathrooms_mode="at_least_minus_one",
        ),
        SearchStageConfig(
            name="same_microzone",
            label="Microzona",
            query=microzone_query,
            stage_priority=1,
            area_tolerance=0.30,
            min_area_delta=15,
            bedrooms_mode="exact",
            bathrooms_mode="at_least_minus_one",
        ),
        SearchStageConfig(
            name="same_local_area",
            label="Área local",
            query=district_query,
            stage_priority=2,
            area_tolerance=0.40,
            min_area_delta=20,
            bedrooms_mode="plus_minus_one",
            bathrooms_mode="at_least_minus_one",
        ),
        SearchStageConfig(
            name="municipality",
            label="Municipio",
            query=municipality_query,
            stage_priority=3,
            area_tolerance=0.45,
            min_area_delta=25,
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


def normalize_tag(text: str) -> str:
    return normalize_space(text).lower()


def parse_listing_signals(
    raw_tags: list[str],
    parking_text: Optional[str],
    description: Optional[str],
    floor_text: Optional[str] = None,
) -> dict:
    """Derive normalized feature signals from SERP tags + parking + description + floor.

    Idealista regularly encodes the elevator state inside the floor detail
    (e.g. ``"Planta 3 exterior con ascensor"``), so we accept ``floor_text``
    and use it as a secondary signal source.
    """
    tags = unique_preserve_order(
        [normalize_tag(tag) for tag in (raw_tags or []) if tag]
    )

    condition = next(
        (CONDITION_MAP[tag] for tag in tags if tag in CONDITION_MAP),
        None,
    )

    has_elevator: Optional[bool] = None
    if any(phrase in tag for tag in tags for phrase in NO_ELEVATOR_PHRASES):
        has_elevator = False
    elif any("ascensor" in tag for tag in tags):
        has_elevator = True

    has_terrace = True if "terraza" in tags else None
    has_pool = True if "piscina" in tags else None

    has_garden: Optional[bool] = (
        True if any("jardin" in tag or "jardín" in tag for tag in tags) else None
    )
    has_storage_room: Optional[bool] = (
        True if any("trastero" in tag for tag in tags) else None
    )

    parking_lower = (parking_text or "").lower()
    if any("garaje" in tag or "parking" in tag or "plaza de" in tag for tag in tags):
        has_garage: Optional[bool] = True
    elif "garaje" in parking_lower or "parking" in parking_lower:
        has_garage = True
    else:
        has_garage = None

    has_ac: Optional[bool] = None
    desc_lower = description.lower() if description else ""
    if desc_lower:
        if any(keyword.strip() in desc_lower for keyword in AC_KEYWORDS):
            has_ac = True
        if has_garden is None and ("jardin" in desc_lower or "jardín" in desc_lower):
            has_garden = True
        if has_storage_room is None and "trastero" in desc_lower:
            has_storage_room = True
        if any(phrase in desc_lower for phrase in NO_ELEVATOR_PHRASES):
            has_elevator = False
        elif has_elevator is None and "con ascensor" in desc_lower:
            has_elevator = True

    floor_lower = floor_text.lower() if floor_text else ""
    if floor_lower:
        if any(phrase in floor_lower for phrase in NO_ELEVATOR_PHRASES):
            has_elevator = False
        elif has_elevator is None and "con ascensor" in floor_lower:
            has_elevator = True

    return {
        "tags": tags,
        "condition": condition,
        "has_elevator": has_elevator,
        "has_terrace": has_terrace,
        "has_pool": has_pool,
        "has_garage": has_garage,
        "has_garden": has_garden,
        "has_storage_room": has_storage_room,
        "has_air_conditioning": has_ac,
    }


def build_listing_from_raw(raw: dict, source_stage: str) -> Optional[Listing]:
    if not raw.get("url"):
        return None

    price = parse_price(raw.get("price", ""))
    listing_m2 = None
    listing_beds = None
    # Idealista's SERP never exposes bathrooms as a structured detail; we rely
    # on the detail-page enrichment step in
    # listing_detail.enrich_listings_with_details and, as a fallback, regex
    # over the (often truncated) SERP description below.
    listing_baths: Optional[int] = extract_bathrooms_from_description(
        raw.get("description")
    )
    floor = None
    raw_parking_detail: Optional[str] = None

    raw_details = raw.get("details", []) or []
    raw_description = raw.get("description")
    logger.info("Listing raw details: %s", raw_details)
    if raw_description:
        logger.info("Listing description (first 200 chars): %s", raw_description[:200])

    floor_word_ascii = {strip_accents(word) for word in FLOOR_WORD_MAP}

    for detail in raw_details:
        detail_lower = detail.lower()
        detail_ascii = strip_accents(detail_lower)

        if "m²" in detail_lower or "m2" in detail_ascii:
            listing_m2 = parse_m2(detail)
        elif "hab" in detail_ascii or "habitacion" in detail_ascii or "dorm" in detail_ascii:
            listing_beds = parse_rooms(detail)
        elif "garaje" in detail_ascii or "parking" in detail_ascii:
            raw_parking_detail = detail
        elif (
            "planta" in detail_ascii
            or "piso" in detail_ascii
            or any(word in detail_ascii for word in floor_word_ascii)
        ):
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

    combined_parking = " ".join(
        part for part in (raw.get("parking"), raw_parking_detail) if part
    ) or None
    signals = parse_listing_signals(
        raw.get("tags", []),
        combined_parking,
        raw.get("description"),
        floor_text=floor,
    )
    floor_number = parse_floor_number(floor)

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
        floor_number=floor_number,
        source_stage=source_stage,
        **signals,
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

    return stage_priority * 55 + area_penalty + bedroom_penalty + bathroom_penalty


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
    threshold = STOP_RULES_BY_STAGE.get(stage.name, TARGET_COMPARABLES)
    if len(ranked_listings) >= max(threshold, TARGET_COMPARABLES if stage.name == "municipality" else threshold):
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

            const collectTextList = (root, selector) => {
                const seen = new Set();
                const values = [];
                root.querySelectorAll(selector).forEach((el) => {
                    const value = (el.textContent || '').replace(/\\s+/g, ' ').trim();
                    if (!value) return;
                    const key = value.toLowerCase();
                    if (seen.has(key)) return;
                    seen.add(key);
                    values.push(value);
                });
                return values;
            };

            const firstText = (root, selector) => {
                const el = root.querySelector(selector);
                if (!el) return null;
                const value = (el.textContent || '').replace(/\\s+/g, ' ').trim();
                return value || null;
            };

            return Array.from(articles).map(article => {
                const linkEl = article.querySelector('a.item-link');
                const priceEl = article.querySelector('.item-price, .price-row .item-price');
                const detailEls = article.querySelectorAll('.item-detail-char .item-detail');
                const imgEl = article.querySelector('.item-gallery img, .item-multimedia img, .item-multimedia-pictures img');
                const details = Array.from(detailEls).map(el => {
                    const text = (el.textContent || '').replace(/\\s+/g, ' ').trim();
                    const tooltipChild = el.querySelector('[aria-label], [title], [data-tooltip-text]');
                    const tooltip = el.getAttribute('data-tooltip-text')
                        || el.getAttribute('title')
                        || el.getAttribute('aria-label')
                        || tooltipChild?.getAttribute('aria-label')
                        || tooltipChild?.getAttribute('title')
                        || tooltipChild?.getAttribute('data-tooltip-text')
                        || '';
                    return tooltip ? `${text} ${tooltip}`.trim() : text;
                });
                const title = linkEl?.getAttribute('title') || linkEl?.textContent?.trim() || null;
                const tags = collectTextList(
                    article,
                    '.item-tags span, .item-tags li, .adv-tags span, .adv-tags li, .item-detail-tags span, .listing-tags span'
                );
                const parking = firstText(
                    article,
                    '.item-parking, .parking-row, .item-detail-parking-row, .parking-included'
                );
                const description = firstText(
                    article,
                    '.item-description, .item-description-text, .description, p.ellipsis'
                );

                return {
                    url: linkEl ? linkEl.getAttribute('href') : null,
                    price: priceEl ? priceEl.textContent.trim() : null,
                    details: details,
                    address: title,
                    image: imgEl ? (imgEl.getAttribute('src') || imgEl.getAttribute('data-src')) : null,
                    title: title,
                    tags: tags,
                    parking: parking,
                    description: description,
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
    except PlaywrightError as exc:
        duration_ms = int((perf_counter() - stage_started_at) * 1000)
        search_url = await extract_search_url(page)
        logger.warning(f"Stage {stage.name} failed at {search_url}: {exc}")
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

    # Imported here to break the scraper <-> listing_detail import cycle.
    from listing_detail import enrich_listings_with_details

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

            ranked_listings = rank_candidates(candidates, max_listings=max_listings)
            ranked_listings = await enrich_listings_with_details(
                browser,
                ranked_listings,
            )
        finally:
            await browser.close()

    total_duration_ms = int((perf_counter() - total_started_at) * 1000)
    final_stage = executed_stages[-1].name if executed_stages else "none"

    search_metadata = SearchMetadata(
        strategy="layered_geography",
        target_comparables=TARGET_COMPARABLES,
        final_stage=final_stage,
        total_duration_ms=total_duration_ms,
        stages=executed_stages,
    )

    logger.info(
        f"Parsed {len(ranked_listings)} ranked listings across {len(executed_stages)} stages in {total_duration_ms}ms"
    )
    return ranked_listings, final_search_url, search_metadata
