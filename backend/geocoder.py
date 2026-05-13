from __future__ import annotations

import unicodedata
import re
import httpx
from models import MunicipioInfo, ResolvedAddress


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
        response = await client.get(PHOTON_ENDPOINT, params=params)
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


async def suggest_addresses(query: str, limit: int = 5) -> list[ResolvedAddress]:
    """
    Returns autocomplete suggestions for an address.

    Primary provider is Photon (autocomplete-optimized, no rate-limit). We fall
    back to Nominatim only when Photon is unreachable, since Nominatim's public
    instance rejects high-frequency autocomplete traffic with HTTP 429.
    """
    import logging
    logger = logging.getLogger(__name__)

    normalized_query = query.strip()
    if len(normalized_query) < 3:
        return []

    capped_limit = max(1, min(limit, 8))

    try:
        photon_suggestions = await search_photon(normalized_query, limit=capped_limit)
        if photon_suggestions:
            return photon_suggestions
    except Exception as exc:
        logger.warning("Photon autocomplete failed, falling back to Nominatim: %s", exc)

    try:
        results = await search_nominatim(normalized_query, limit=capped_limit)
        if not results:
            results = await search_nominatim_unrestricted(normalized_query, limit=capped_limit)
    except Exception as exc:
        logger.warning("Nominatim fallback also failed: %s", exc)
        return []

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
