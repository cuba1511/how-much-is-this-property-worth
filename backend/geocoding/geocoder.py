from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import unicodedata
from collections import OrderedDict

import httpx

from models import MunicipioInfo, ResolvedAddress

logger = logging.getLogger(__name__)


# Street-type / filler tokens that don't help Photon match a specific address
# (they appear in thousands of street names and only add noise to the query).
# Covers ES + CA + common abbreviations.
_STREET_FILLER_TOKENS = {
    "calle", "c", "c/", "c.",
    "carrer",
    "avenida", "avda", "av", "av.",
    "avinguda",
    "plaza", "pza", "plza",
    "plaça", "pl", "pl.",
    "paseo", "pº", "po",
    "passeig",
    "ronda",
    "camino", "cami", "camí",
    "travesia", "travesía", "travessera",
    "calleja", "callejon", "callejón",
    "via", "vía",
    "glorieta",
    "bulevar", "boulevard",
}


def _strip_street_fillers(query: str) -> str:
    """Remove street-type prefix tokens (calle, carrer, av, etc.) from a query.

    Photon matches every token, so generic prefixes dilute the result set with
    thousands of unrelated streets. Stripping them dramatically improves recall
    when the user types things like "carrer Sant Joan d'Àustria 101" — what we
    actually want to send is "Sant Joan d'Àustria 101".
    """
    if not query:
        return query
    tokens = re.split(r"\s+", query.strip())
    kept: list[str] = []
    for tok in tokens:
        normalized = tok.lower().rstrip(".,").strip()
        if normalized in _STREET_FILLER_TOKENS:
            continue
        kept.append(tok)
    return " ".join(kept).strip()


def slugify(text: str) -> str:
    """Convert a Spanish municipality name to an Idealista-compatible URL slug."""
    # Normalize unicode (decompose accented characters)
    normalized = unicodedata.normalize("NFD", text)
    # Keep only ASCII characters
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    # Lowercase and replace spaces/special chars with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug


def normalize_text(text: str) -> str:
    return slugify(text or "").replace("-", " ")


def nominatim_headers() -> dict:
    return {
        "User-Agent": "HouseValuationMVP/1.0 (contact@prophero.com)"
    }


def extract_address_hints(address: str) -> dict:
    parts = [part.strip() for part in address.split(",") if part.strip()]
    first_part = parts[0] if parts else address
    tail_parts = parts[1:] if len(parts) > 1 else []

    postcode_match = re.search(r"\b(\d{5})\b", address)
    road_hint = re.sub(r"\b\d+[A-Za-z0-9/-]*\b", "", first_part).strip(" ,")

    return {
        "road_hint": normalize_text(road_hint),
        "parts": [normalize_text(part) for part in parts],
        "tail_parts": [normalize_text(part) for part in tail_parts],
        "postcode": postcode_match.group(1) if postcode_match else None,
        "locality_hint": normalize_text(parts[-1]) if parts else "",
    }


def get_result_locality(addr: dict) -> str:
    return normalize_text(
        addr.get("city")
        or addr.get("town")
        or addr.get("village")
        or addr.get("municipality")
        or addr.get("county")
        or ""
    )


def score_nominatim_result(result: dict, hints: dict) -> int:
    addr = result.get("address", {})
    score = 0

    locality = get_result_locality(addr)
    province = normalize_text(addr.get("province") or addr.get("state") or "")
    road = normalize_text(addr.get("road") or "")
    neighbourhood = normalize_text(addr.get("neighbourhood") or addr.get("suburb") or "")
    quarter = normalize_text(addr.get("quarter") or "")
    city_district = normalize_text(addr.get("city_district") or "")
    postcode = addr.get("postcode")

    if hints["postcode"] and postcode == hints["postcode"]:
        score += 100

    for token in hints["tail_parts"]:
        if token and token == locality:
            score += 40
        if token and token == province:
            score += 18
        if token and token in {neighbourhood, quarter, city_district}:
            score += 10

    if hints["road_hint"] and road and hints["road_hint"] in road:
        score += 18

    if result.get("importance") is not None:
        score += int(float(result.get("importance", 0)) * 10)

    return score


def pick_best_nominatim_result(results: list[dict], address: str) -> dict:
    hints = extract_address_hints(address)
    if len(results) == 1:
        return results[0]

    ranked = sorted(
        results,
        key=lambda result: score_nominatim_result(result, hints),
        reverse=True,
    )
    return ranked[0]


async def search_nominatim(query: str, *, limit: int) -> list[dict]:
    params = {
        "q": query,
        "format": "json",
        "addressdetails": 1,
        "limit": limit,
        "countrycodes": "es",
    }

    async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
        response = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params=params,
            headers=nominatim_headers(),
        )
        response.raise_for_status()
        return response.json()


async def search_nominatim_unrestricted(query: str, *, limit: int) -> list[dict]:
    params = {
        "q": query,
        "format": "json",
        "addressdetails": 1,
        "limit": limit,
    }

    async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
        response = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params=params,
            headers=nominatim_headers(),
        )
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Photon (Komoot) — used for autocomplete suggestions.
#
# Photon is OSM-backed (same data as Nominatim) but, unlike Nominatim's public
# instance, it is *designed* for typeahead/autocomplete usage and does not
# enforce the 1 req/s policy that breaks browser autocomplete UX. It is the
# provider Nominatim itself recommends for autocomplete:
#   https://operations.osmfoundation.org/policies/nominatim/
# ---------------------------------------------------------------------------

PHOTON_ENDPOINT = "https://photon.komoot.io/api/"


def _photon_label(props: dict) -> str:
    segments: list[str] = []

    street = props.get("street")
    housenumber = props.get("housenumber")
    street_line = " ".join(part for part in [street, housenumber] if part)
    if street_line:
        segments.append(street_line)
    elif props.get("name"):
        segments.append(props["name"])

    locality = (
        props.get("city")
        or props.get("town")
        or props.get("village")
        or props.get("county")
    )
    if locality and locality not in segments:
        segments.append(locality)

    state = props.get("state")
    if state and state != locality:
        segments.append(state)

    postcode = props.get("postcode")
    if postcode:
        segments.append(postcode)

    country = props.get("country")
    if country and country not in {"España", "Spain"}:
        segments.append(country)

    return ", ".join(s for s in segments if s)


def _photon_feature_to_resolved(feature: dict) -> ResolvedAddress | None:
    geometry = feature.get("geometry") or {}
    coords = geometry.get("coordinates") or []
    if len(coords) < 2:
        return None
    lon, lat = float(coords[0]), float(coords[1])

    props = feature.get("properties") or {}
    municipality = (
        props.get("city")
        or props.get("town")
        or props.get("village")
        or props.get("county")
        or props.get("state")
        or props.get("name")
        or ""
    )

    label = _photon_label(props) or municipality or props.get("name") or ""
    if not label:
        return None

    osm_id = props.get("osm_id")
    osm_type = props.get("osm_type")
    provider_id = f"{osm_type}{osm_id}" if osm_id is not None and osm_type else None

    return ResolvedAddress(
        label=label,
        lat=lat,
        lon=lon,
        municipality=municipality or label,
        province=props.get("state"),
        road=props.get("street"),
        house_number=props.get("housenumber"),
        postcode=props.get("postcode"),
        neighbourhood=props.get("district"),
        quarter=None,
        city_district=props.get("district"),
        country=props.get("country"),
        provider="photon",
        provider_id=provider_id,
        precision=props.get("osm_value") or props.get("type"),
    )


def _photon_headers() -> dict:
    # Identify ourselves explicitly. httpx's default UA ("python-httpx/x.x") is
    # the kind of token Cloudflare/Komoot occasionally throttles to a hard 403,
    # which is exactly what we were seeing in prod. A real UA + a Referer that
    # points to our own product makes us look like a normal app, not a bot.
    return {
        "User-Agent": "HouseValuationMVP/1.0 (contact@prophero.com)",
        "Referer": "https://prophero.com",
        "Accept": "application/json",
    }


async def search_photon(query: str, *, limit: int) -> list[ResolvedAddress]:
    """Autocomplete-friendly geocoder backed by Komoot's Photon (OSM data)."""
    params = {
        "q": query,
        "limit": limit,
        # Photon only supports default/de/en/fr. "default" returns names in their
        # native language (perfect for ES results).
        "lang": "default",
    }

    async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
        response = await client.get(
            PHOTON_ENDPOINT,
            params=params,
            headers=_photon_headers(),
        )
        response.raise_for_status()
        payload = response.json()

    features = payload.get("features") or []
    suggestions: list[ResolvedAddress] = []
    seen_labels: set[str] = set()
    for feature in features:
        props = feature.get("properties") or {}
        # Restrict to Spanish results — the rest of the pipeline (Idealista
        # slug, valuations) only handles ES.
        if props.get("countrycode") and props["countrycode"] != "ES":
            continue
        resolved = _photon_feature_to_resolved(feature)
        if not resolved or resolved.label in seen_labels:
            continue
        seen_labels.add(resolved.label)
        suggestions.append(resolved)
        if len(suggestions) >= limit:
            break
    return suggestions


async def reverse_nominatim(lat: float, lon: float) -> dict | None:
    params = {
        "lat": lat,
        "lon": lon,
        "format": "json",
        "addressdetails": 1,
        "zoom": 18,
    }

    async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
        response = await client.get(
            "https://nominatim.openstreetmap.org/reverse",
            params=params,
            headers=nominatim_headers(),
        )
        response.raise_for_status()
        data = response.json()
    return data if data.get("address") else None


def locality_matches_hint(result: dict, locality_hint: str) -> bool:
    if not locality_hint:
        return True
    locality = get_result_locality(result.get("address", {}))
    return locality == locality_hint


def extract_municipio_from_nominatim(address_data: dict) -> dict:
    """
    Nominatim returns nested address fields. Priority order for Spanish municipios:
    city > town > village > municipality > county
    """
    addr = address_data.get("address", {})

    name = (
        addr.get("city")
        or addr.get("town")
        or addr.get("village")
        or addr.get("municipality")
        or addr.get("county")
        or addr.get("state")
        or "Unknown"
    )

    province = addr.get("province") or addr.get("state") or None

    return {
        "name": name,
        "province": province,
        "lat": float(address_data.get("lat", 0)),
        "lon": float(address_data.get("lon", 0)),
        "road": addr.get("road"),
        "house_number": addr.get("house_number"),
        "neighbourhood": addr.get("neighbourhood") or addr.get("suburb"),
        "quarter": addr.get("quarter"),
        "city_district": addr.get("city_district"),
        "postcode": addr.get("postcode"),
        "country": addr.get("country"),
        "provider_id": str(address_data.get("place_id")) if address_data.get("place_id") else None,
        "precision": address_data.get("type"),
    }


def build_address_label(addr: dict) -> str:
    segments = []

    road = addr.get("road")
    house_number = addr.get("house_number")
    street = " ".join(part for part in [road, house_number] if part)
    if street:
        segments.append(street)

    locality = (
        addr.get("city")
        or addr.get("town")
        or addr.get("village")
        or addr.get("municipality")
        or addr.get("county")
    )
    if locality:
        segments.append(locality)

    province = addr.get("province") or addr.get("state")
    if province and province != locality:
        segments.append(province)

    postcode = addr.get("postcode")
    if postcode:
        segments.append(postcode)

    country = addr.get("country")
    if country and country != "España":
        segments.append(country)

    return ", ".join(segment for segment in segments if segment)


def resolved_address_from_nominatim(result: dict) -> ResolvedAddress:
    info = extract_municipio_from_nominatim(result)
    municipality = info["name"]
    addr = result.get("address", {})
    label = build_address_label(addr) or result.get("display_name") or municipality

    return ResolvedAddress(
        label=label,
        lat=info["lat"],
        lon=info["lon"],
        municipality=municipality,
        province=info["province"],
        road=info["road"],
        house_number=info["house_number"],
        postcode=info["postcode"],
        neighbourhood=info["neighbourhood"],
        quarter=info["quarter"],
        city_district=info["city_district"],
        country=info["country"],
        provider_id=info["provider_id"],
        precision=info["precision"],
    )


def municipio_from_resolved_address(address: ResolvedAddress) -> MunicipioInfo:
    return MunicipioInfo(
        name=address.municipality,
        slug=slugify(address.municipality),
        province=address.province,
        lat=address.lat,
        lon=address.lon,
        road=address.road,
        neighbourhood=address.neighbourhood,
        quarter=address.quarter,
        city_district=address.city_district,
        postcode=address.postcode,
    )


# ---------------------------------------------------------------------------
# MapTiler & LocationIQ — optional providers gated behind API keys.
#
# Both Photon (Komoot) and the public Nominatim instance regularly throttle
# autocomplete traffic from commercial IPs (Photon → 403 Cloudflare block,
# Nominatim → 429 after >1 req/s). When an API key is configured we use these
# providers first to bypass the public-instance limits entirely.
#
# MapTiler:   https://docs.maptiler.com/cloud/api/geocoding/   (100k req/mo free)
# LocationIQ: https://locationiq.com/docs                       (5k req/day free)
# ---------------------------------------------------------------------------

MAPTILER_ENDPOINT = "https://api.maptiler.com/geocoding/{query}.json"
LOCATIONIQ_ENDPOINT = "https://api.locationiq.com/v1/autocomplete"


def _maptiler_feature_to_resolved(feature: dict) -> ResolvedAddress | None:
    geometry = feature.get("geometry") or {}
    coords = geometry.get("coordinates") or []
    if len(coords) < 2:
        return None
    lon, lat = float(coords[0]), float(coords[1])

    props = feature.get("properties") or {}
    place_name = feature.get("place_name") or feature.get("text") or ""

    context = {ctx.get("kind") or ctx.get("id", "").split(".")[0]: ctx for ctx in feature.get("context", []) if isinstance(ctx, dict)}

    def ctx_text(kind: str) -> str | None:
        item = context.get(kind)
        return item.get("text") if item else None

    municipality = (
        ctx_text("municipality")
        or ctx_text("place")
        or ctx_text("locality")
        or ctx_text("city")
        or props.get("place_type_name")
        or ""
    )
    province = ctx_text("region") or ctx_text("subregion") or props.get("region")
    postcode = ctx_text("postal_code") or props.get("postal_code")
    country = ctx_text("country") or props.get("country")

    if not place_name:
        return None

    return ResolvedAddress(
        label=place_name,
        lat=lat,
        lon=lon,
        municipality=municipality or place_name,
        province=province,
        road=props.get("street") or feature.get("text"),
        house_number=props.get("address") or feature.get("address"),
        postcode=postcode,
        neighbourhood=ctx_text("neighborhood") or ctx_text("neighbourhood"),
        quarter=None,
        city_district=ctx_text("district"),
        country=country,
        provider="maptiler",
        provider_id=str(feature.get("id")) if feature.get("id") is not None else None,
        precision=feature.get("place_type", [None])[0] if isinstance(feature.get("place_type"), list) else None,
    )


async def search_maptiler(query: str, *, limit: int) -> list[ResolvedAddress]:
    api_key = os.getenv("MAPTILER_API_KEY")
    if not api_key:
        return []

    # MapTiler embeds the query in the URL path; httpx URL-encodes path segments
    # automatically when we build the URL via copy_with().
    base_url = httpx.URL("https://api.maptiler.com/geocoding/")
    url = base_url.join(f"{query}.json")
    params = {
        "key": api_key,
        "country": "es",
        "language": "es",
        "limit": limit,
        "autocomplete": "true",
    }

    async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()

    features = payload.get("features") or []
    suggestions: list[ResolvedAddress] = []
    seen: set[str] = set()
    for feature in features:
        resolved = _maptiler_feature_to_resolved(feature)
        if not resolved:
            continue
        key = resolved.provider_id or resolved.label
        if key in seen:
            continue
        seen.add(key)
        suggestions.append(resolved)
        if len(suggestions) >= limit:
            break
    return suggestions


def _locationiq_to_resolved(item: dict) -> ResolvedAddress | None:
    try:
        lat = float(item.get("lat"))
        lon = float(item.get("lon"))
    except (TypeError, ValueError):
        return None

    addr = item.get("address") or {}
    label = item.get("display_name") or item.get("display_place") or ""
    if not label:
        return None

    municipality = (
        addr.get("city")
        or addr.get("town")
        or addr.get("village")
        or addr.get("municipality")
        or addr.get("county")
        or ""
    )

    return ResolvedAddress(
        label=label,
        lat=lat,
        lon=lon,
        municipality=municipality or label,
        province=addr.get("state") or addr.get("region"),
        road=addr.get("road") or addr.get("street") or addr.get("name"),
        house_number=addr.get("house_number"),
        postcode=addr.get("postcode"),
        neighbourhood=addr.get("neighbourhood") or addr.get("suburb"),
        quarter=addr.get("quarter"),
        city_district=addr.get("city_district") or addr.get("district"),
        country=addr.get("country"),
        provider="locationiq",
        provider_id=str(item.get("place_id")) if item.get("place_id") else None,
        precision=item.get("type") or item.get("class"),
    )


async def search_locationiq(query: str, *, limit: int) -> list[ResolvedAddress]:
    api_key = os.getenv("LOCATIONIQ_API_KEY")
    if not api_key:
        return []

    params = {
        "key": api_key,
        "q": query,
        "limit": limit,
        "countrycodes": "es",
        "format": "json",
        "addressdetails": 1,
        "normalizecity": 1,
        "tag": "place:*,highway:*,building:*",
    }

    async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
        response = await client.get(LOCATIONIQ_ENDPOINT, params=params)
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, list):
        return []

    suggestions: list[ResolvedAddress] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        resolved = _locationiq_to_resolved(item)
        if not resolved:
            continue
        key = resolved.provider_id or resolved.label
        if key in seen:
            continue
        seen.add(key)
        suggestions.append(resolved)
        if len(suggestions) >= limit:
            break
    return suggestions


# ---------------------------------------------------------------------------
# Autocomplete cache + in-flight dedupe.
#
# Without this, every keystroke ("p", "po", "pon", "ponc", ...) becomes a
# separate upstream request. With debounce + a small server-side TTL cache,
# typing "ponciano" only fires ~1-2 upstream calls instead of 7+.
# ---------------------------------------------------------------------------

_AUTOCOMPLETE_CACHE_MAX = 1024
_AUTOCOMPLETE_CACHE_TTL_HIT = 300.0   # 5 min for results we want to reuse
_AUTOCOMPLETE_CACHE_TTL_MISS = 30.0   # 30 s for empty/errored results

# OrderedDict acts as a tiny LRU.
_autocomplete_cache: "OrderedDict[tuple[str, int], tuple[float, list[ResolvedAddress]]]" = OrderedDict()
_autocomplete_cache_lock = asyncio.Lock()
_autocomplete_inflight: dict[tuple[str, int], asyncio.Future[list[ResolvedAddress]]] = {}


def _autocomplete_cache_key(query: str, limit: int) -> tuple[str, int]:
    return (query.strip().lower(), limit)


async def _cache_get(key: tuple[str, int]) -> list[ResolvedAddress] | None:
    async with _autocomplete_cache_lock:
        entry = _autocomplete_cache.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if expires_at < time.monotonic():
            _autocomplete_cache.pop(key, None)
            return None
        _autocomplete_cache.move_to_end(key)
        return value


async def _cache_put(key: tuple[str, int], value: list[ResolvedAddress]) -> None:
    ttl = _AUTOCOMPLETE_CACHE_TTL_HIT if value else _AUTOCOMPLETE_CACHE_TTL_MISS
    async with _autocomplete_cache_lock:
        _autocomplete_cache[key] = (time.monotonic() + ttl, value)
        _autocomplete_cache.move_to_end(key)
        while len(_autocomplete_cache) > _AUTOCOMPLETE_CACHE_MAX:
            _autocomplete_cache.popitem(last=False)


async def _photon_chain(normalized_query: str, capped_limit: int) -> list[ResolvedAddress]:
    """Run the original + filler-stripped Photon queries in parallel."""
    cleaned_query = _strip_street_fillers(normalized_query)
    queries = [normalized_query]
    if cleaned_query and cleaned_query.lower() != normalized_query.lower():
        queries.append(cleaned_query)

    results = await asyncio.gather(
        *(search_photon(q, limit=capped_limit) for q in queries),
        return_exceptions=True,
    )
    merged: list[ResolvedAddress] = []
    seen_keys: set[str] = set()
    any_success = False
    any_failure = False
    for res in results:
        if isinstance(res, Exception):
            any_failure = True
            logger.warning("Photon autocomplete query failed: %s", res)
            continue
        any_success = True
        for suggestion in res:
            key = suggestion.provider_id or suggestion.label
            if key in seen_keys:
                continue
            seen_keys.add(key)
            merged.append(suggestion)

    if merged:
        return merged[:capped_limit]
    if any_success and not any_failure:
        # Photon answered but had nothing; signal "empty, don't fall through".
        return []
    # All queries failed → bubble up so the caller falls back to Nominatim.
    raise RuntimeError("Photon returned no successful responses")


async def _nominatim_chain(normalized_query: str, capped_limit: int) -> list[ResolvedAddress]:
    results = await search_nominatim(normalized_query, limit=capped_limit)
    if not results:
        results = await search_nominatim_unrestricted(normalized_query, limit=capped_limit)

    suggestions: list[ResolvedAddress] = []
    seen_labels: set[str] = set()
    for result in results:
        suggestion = resolved_address_from_nominatim(result)
        if suggestion.label in seen_labels:
            continue
        seen_labels.add(suggestion.label)
        suggestions.append(suggestion)
        if len(suggestions) >= capped_limit:
            break
    return suggestions


async def _suggest_addresses_uncached(
    normalized_query: str,
    capped_limit: int,
) -> list[ResolvedAddress]:
    """Provider chain. First non-empty result wins; failures cascade.

    Order is intentional: API-key providers first (rate-limit-free), then free
    public instances. Each step is best-effort; we never let one provider's
    outage block the whole chain.
    """

    if os.getenv("MAPTILER_API_KEY"):
        try:
            results = await search_maptiler(normalized_query, limit=capped_limit)
            if results:
                return results
        except Exception as exc:
            logger.warning("MapTiler autocomplete failed: %s", exc)

    if os.getenv("LOCATIONIQ_API_KEY"):
        try:
            results = await search_locationiq(normalized_query, limit=capped_limit)
            if results:
                return results
        except Exception as exc:
            logger.warning("LocationIQ autocomplete failed: %s", exc)

    try:
        results = await _photon_chain(normalized_query, capped_limit)
        if results:
            return results
    except Exception as exc:
        logger.warning("Photon autocomplete failed, falling back to Nominatim: %s", exc)

    try:
        return await _nominatim_chain(normalized_query, capped_limit)
    except Exception as exc:
        logger.warning("Nominatim fallback also failed: %s", exc)
        return []


async def suggest_addresses(query: str, limit: int = 5) -> list[ResolvedAddress]:
    """
    Returns autocomplete suggestions for an address.

    The provider chain is, in order: MapTiler (if MAPTILER_API_KEY set) →
    LocationIQ (if LOCATIONIQ_API_KEY set) → Photon → Nominatim. The first two
    are commercial providers with API keys; without them, we fall back to the
    free public Photon/Nominatim instances which can return 403/429 from
    commercial IPs.

    A small in-process TTL cache + in-flight dedupe absorbs autocomplete bursts
    (one cached prefix serves N keystrokes). Empty/error responses are cached
    for a short TTL to avoid hammering throttled providers on each keystroke.
    """
    normalized_query = query.strip()
    if len(normalized_query) < 3:
        return []

    capped_limit = max(1, min(limit, 8))
    cache_key = _autocomplete_cache_key(normalized_query, capped_limit)

    cached = await _cache_get(cache_key)
    if cached is not None:
        return list(cached)

    inflight = _autocomplete_inflight.get(cache_key)
    if inflight is not None:
        return list(await inflight)

    loop = asyncio.get_running_loop()
    future: asyncio.Future[list[ResolvedAddress]] = loop.create_future()
    _autocomplete_inflight[cache_key] = future

    try:
        result = await _suggest_addresses_uncached(normalized_query, capped_limit)
        await _cache_put(cache_key, result)
        if not future.done():
            future.set_result(result)
        return result
    except Exception as exc:
        if not future.done():
            future.set_exception(exc)
        raise
    finally:
        _autocomplete_inflight.pop(cache_key, None)


async def reverse_geocode(lat: float, lon: float) -> ResolvedAddress:
    result = await reverse_nominatim(lat, lon)
    if not result:
        raise ValueError("Could not resolve coordinates to an address")
    return resolved_address_from_nominatim(result)


async def get_municipio_from_address(address: str) -> MunicipioInfo:
    """
    Geocodes the given address using Nominatim (OpenStreetMap) and returns
    a MunicipioInfo with the name and Idealista URL slug.
    """
    hints = extract_address_hints(address)
    results = await search_nominatim(address, limit=8)

    if not results:
        results = await search_nominatim_unrestricted(address, limit=8)

    if not results:
        raise ValueError(f"Could not geocode address: {address}")

    best_result = pick_best_nominatim_result(results, address)

    if hints["locality_hint"] and not locality_matches_hint(best_result, hints["locality_hint"]):
        locality_results = await search_nominatim(hints["locality_hint"], limit=5)
        if locality_results:
            best_result = pick_best_nominatim_result(locality_results, hints["locality_hint"])

    info = extract_municipio_from_nominatim(best_result)

    return MunicipioInfo(
        name=info["name"],
        slug=slugify(info["name"]),
        province=info["province"],
        lat=info["lat"],
        lon=info["lon"],
        road=info["road"],
        neighbourhood=info["neighbourhood"],
        quarter=info["quarter"],
        city_district=info["city_district"],
        postcode=info["postcode"],
    )
