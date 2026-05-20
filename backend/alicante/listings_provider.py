"""Local-dataset comparables provider for the Alicante MVP.

Same signature as `scraping.scraper.scrape_idealista_listings` so the
Alicante endpoint can swap providers without touching the response-building
code in `routes.py`. The provider performs:

1. Bounding-box pre-filter in SQL (cheap, uses the `(lat, lon)` index).
2. Haversine distance ranking + soft scoring in Python (similar to the
   scraper's `score_listing`).
3. Row-to-`Listing` mapping that preserves the `models.Listing` contract.

The provider is `async` only to match the scraper's signature — SQLite
calls are sync but fast (<50ms).
"""
from __future__ import annotations

import logging
import math
from time import perf_counter
from typing import Optional
from urllib.parse import quote

from models import Listing, MunicipioInfo, SearchMetadata, SearchStageResult

from alicante import storage

logger = logging.getLogger(__name__)

# ── Tuning knobs (mirrors the scraper's defaults) ────────────────────────
# Half-side of the lat/lon bounding box (degrees). 0.025° ≈ 2.8 km at 38°N.
DEFAULT_BBOX_HALF_DEG = 0.025
WIDE_BBOX_HALF_DEG = 0.07  # ~7.8 km — used when the tight box is too sparse
# Area tolerance: ±25% but never less than ±15 m².
AREA_TOLERANCE_PCT = 0.25
MIN_AREA_DELTA = 15
# Rooms/baths tolerance: ±1, mirroring the scraper's "plus_minus_one".
ROOMS_DELTA = 1
BATHS_DELTA = 1
# Minimum sample size in the strict box before we widen.
MIN_SAMPLE_TIGHT = 6
# Default property_type filter when nothing else applies.
DEFAULT_PROPERTY_TYPE = "Pisos"

# Alicante centroid — fallback when the geocoder doesn't return lat/lon for
# the property. ~Mercado district.
ALICANTE_FALLBACK_LAT = 38.345
ALICANTE_FALLBACK_LON = -0.481

IDEALISTA_BASE = "https://www.idealista.com"


# ────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance between two WGS84 points in meters."""
    r = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _compute_area_window(m2: Optional[int]) -> tuple[Optional[int], Optional[int]]:
    if not m2:
        return None, None
    delta = max(MIN_AREA_DELTA, int(round(m2 * AREA_TOLERANCE_PCT)))
    return max(1, m2 - delta), m2 + delta


def _resolve_anchor_coords(municipio: MunicipioInfo) -> tuple[float, float]:
    if municipio.lat is not None and municipio.lon is not None:
        return municipio.lat, municipio.lon
    return ALICANTE_FALLBACK_LAT, ALICANTE_FALLBACK_LON


def _row_to_listing(
    row: dict,
    *,
    source_stage: str,
    distance_m: Optional[int] = None,
) -> Optional[Listing]:
    price = row.get("local_price")
    area = row.get("area")
    if not price or not area:
        return None

    price_per_m2 = int(price / area) if area > 0 else None
    address = row.get("full_address") or row.get("admin4")
    title = (
        row.get("title")
        or (f"{row.get('property_type_name') or 'Anuncio'} en {address}" if address else "Anuncio")
    )

    conservation = row.get("conservation_name")
    condition = None
    if conservation:
        c = conservation.lower()
        if "buen" in c:
            condition = "segunda_mano"
        elif "reformar" in c:
            condition = "a_reformar"
        elif "nuev" in c or "obra" in c:
            condition = "obra_nueva"

    origin_id = row.get("origin_id") or row.get("gsraw_id")
    listing_url = (
        f"{IDEALISTA_BASE}/inmueble/{origin_id}/"
        if origin_id and str(origin_id).isdigit()
        else f"{IDEALISTA_BASE}/buscar/?q={quote(address or '', safe='')}"
    )

    tags: list[str] = []
    if distance_m is not None:
        tags.append(f"alicante-dataset:{int(distance_m)}m")
    if row.get("delivery_week"):
        tags.append(f"snapshot:{row['delivery_week']}")
    if row.get("admin4"):
        tags.append(row["admin4"])

    def _opt_bool(value) -> Optional[bool]:
        if value is None:
            return None
        return bool(value)

    return Listing(
        title=title[:200],
        price=int(price),
        m2=int(area),
        price_per_m2=price_per_m2,
        bedrooms=int(row["n_rooms"]) if row.get("n_rooms") is not None else None,
        bathrooms=int(row["n_baths"]) if row.get("n_baths") is not None else None,
        address=address,
        url=listing_url,
        image_url=row.get("first_image_url") or None,
        floor=row.get("n_floor") or None,
        source_stage=source_stage,
        tags=tags,
        condition=condition,
        has_elevator=_opt_bool(row.get("has_elevator")),
        has_terrace=_opt_bool(row.get("has_terrace")),
        has_pool=_opt_bool(row.get("has_pool")),
        has_garage=_opt_bool(row.get("has_garage")),
        has_garden=None,
        has_storage_room=_opt_bool(row.get("has_storage")),
        has_air_conditioning=_opt_bool(row.get("has_air_conditioner")),
    )


def _score(
    listing: Listing,
    *,
    distance_m: float,
    target_m2: Optional[int],
    target_bedrooms: Optional[int],
    target_bathrooms: Optional[int],
) -> float:
    """Lower is better. Mirrors the scraper's `score_listing` semantics."""
    area_penalty = 20.0
    if listing.m2 and target_m2:
        area_penalty = abs(listing.m2 - target_m2) / max(target_m2, 1) * 100

    bedroom_penalty = 6.0
    if listing.bedrooms is not None and target_bedrooms is not None:
        bedroom_penalty = abs(listing.bedrooms - target_bedrooms) * 12

    bathroom_penalty = 4.0
    if listing.bathrooms is not None and target_bathrooms is not None:
        bathroom_penalty = abs(listing.bathrooms - target_bathrooms) * 10

    # 50 points per km of distance — comparable in magnitude to area/room
    # penalties so all three matter together.
    distance_penalty = (distance_m / 1000.0) * 50.0

    return area_penalty + bedroom_penalty + bathroom_penalty + distance_penalty


# ────────────────────────────────────────────────────────────────────────
# Public entry point — same signature as scrape_idealista_listings
# ────────────────────────────────────────────────────────────────────────


async def query_alicante_listings(
    address: str,
    *,
    municipio: MunicipioInfo,
    bedrooms: Optional[int] = None,
    bathrooms: Optional[int] = None,
    m2: Optional[int] = None,
    max_listings: int = 10,
    enrich_details: bool = True,  # accepted for signature parity; unused
) -> tuple[list[Listing], str, SearchMetadata]:
    """Pick comparables for an Alicante property from the local SQLite snapshot.

    Returns the same `(listings, search_url, search_metadata)` tuple as
    `scrape_idealista_listings` so the Alicante route can use it as a
    drop-in for the response-building code.
    """
    started_at = perf_counter()
    anchor_lat, anchor_lon = _resolve_anchor_coords(municipio)
    area_min, area_max = _compute_area_window(m2)
    rooms_min = max(0, bedrooms - ROOMS_DELTA) if bedrooms is not None else None
    rooms_max = bedrooms + ROOMS_DELTA if bedrooms is not None else None
    baths_min = max(1, bathrooms - BATHS_DELTA) if bathrooms is not None else None
    baths_max = bathrooms + BATHS_DELTA if bathrooms is not None else None

    stages: list[SearchStageResult] = []

    def _run_box(*, half_deg: float, label: str, name: str) -> list[Listing]:
        stage_started = perf_counter()
        lat_min = anchor_lat - half_deg
        lat_max = anchor_lat + half_deg
        lon_min = anchor_lon - half_deg
        lon_max = anchor_lon + half_deg

        raw_rows = storage.query_listings_raw(
            lat_min=lat_min,
            lat_max=lat_max,
            lon_min=lon_min,
            lon_max=lon_max,
            area_min=area_min,
            area_max=area_max,
            rooms_min=rooms_min,
            rooms_max=rooms_max,
            baths_min=baths_min,
            baths_max=baths_max,
            property_type=DEFAULT_PROPERTY_TYPE,
            limit=500,
        )

        # Decorate rows with distance, dedupe by gsraw_id, drop the anchor itself.
        decorated: list[tuple[float, dict]] = []
        seen: set[str] = set()
        for row in raw_rows:
            gid = row.get("gsraw_id")
            if not gid or gid in seen:
                continue
            seen.add(gid)
            lat = row.get("lat")
            lon = row.get("lon")
            if lat is None or lon is None:
                continue
            distance = _haversine_m(anchor_lat, anchor_lon, float(lat), float(lon))
            decorated.append((distance, row))

        decorated.sort(key=lambda t: t[0])

        listings: list[tuple[float, Listing]] = []
        for distance, row in decorated:
            listing = _row_to_listing(row, source_stage=name, distance_m=int(distance))
            if listing is None:
                continue
            score = _score(
                listing,
                distance_m=distance,
                target_m2=m2,
                target_bedrooms=bedrooms,
                target_bathrooms=bathrooms,
            )
            listings.append((score, listing))

        listings.sort(key=lambda t: t[0])
        ranked = [lst for _, lst in listings[:max_listings]]

        search_query = f"{address or municipio.name}, {municipio.name}"
        search_url = (
            f"{IDEALISTA_BASE}/buscar/venta-viviendas/"
            f"{quote(municipio.slug.replace('-', '_'))}/"
        )
        stages.append(
            SearchStageResult(
                name=name,
                label=label,
                query=search_query,
                search_url=search_url,
                listings_found=len(ranked),
                duration_ms=int((perf_counter() - stage_started) * 1000),
                area_min=area_min,
                area_max=area_max,
                bedrooms_mode="plus_minus_one",
                bathrooms_mode="plus_minus_one",
            )
        )
        return ranked

    # Stage 1: tight box (~2.8 km).
    ranked = _run_box(
        half_deg=DEFAULT_BBOX_HALF_DEG,
        label="Cerca de la dirección",
        name="alicante_local_box",
    )

    # Stage 2: wider box if we don't have enough comparables.
    if len(ranked) < MIN_SAMPLE_TIGHT:
        ranked = _run_box(
            half_deg=WIDE_BBOX_HALF_DEG,
            label="Municipio (Alicante)",
            name="alicante_municipality",
        )

    total_ms = int((perf_counter() - started_at) * 1000)
    final_stage = stages[-1].name if stages else "alicante_local_box"
    search_url = stages[-1].search_url if stages else IDEALISTA_BASE
    search_metadata = SearchMetadata(
        strategy="alicante_local_dataset",
        target_comparables=max_listings,
        final_stage=final_stage,
        total_duration_ms=total_ms,
        stages=stages,
    )

    logger.info(
        "Alicante dataset returned %d comparables for %s in %dms (anchor %.4f,%.4f)",
        len(ranked), address, total_ms, anchor_lat, anchor_lon,
    )
    return ranked, search_url, search_metadata


__all__ = [
    "ALICANTE_FALLBACK_LAT",
    "ALICANTE_FALLBACK_LON",
    "query_alicante_listings",
]
