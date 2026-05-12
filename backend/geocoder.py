import unicodedata
import re
import httpx
from models import MunicipioInfo


def slugify(text: str) -> str:
    """Convert a Spanish municipality name to an Idealista-compatible URL slug."""
    # Normalize unicode (decompose accented characters)
    normalized = unicodedata.normalize("NFD", text)
    # Keep only ASCII characters
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    # Lowercase and replace spaces/special chars with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug


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
        "neighbourhood": addr.get("neighbourhood") or addr.get("suburb"),
        "quarter": addr.get("quarter"),
        "city_district": addr.get("city_district"),
        "postcode": addr.get("postcode"),
    }


async def get_municipio_from_address(address: str) -> MunicipioInfo:
    """
    Geocodes the given address using Nominatim (OpenStreetMap) and returns
    a MunicipioInfo with the name and Idealista URL slug.
    """
    params = {
        "q": address,
        "format": "json",
        "addressdetails": 1,
        "limit": 1,
        "countrycodes": "es",
    }

    headers = {
        # Nominatim requires a descriptive User-Agent
        "User-Agent": "HouseValuationMVP/1.0 (contact@prophero.com)"
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params=params,
            headers=headers,
        )
        response.raise_for_status()
        results = response.json()

    if not results:
        # Fallback: try without countrycodes restriction
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={**params, "countrycodes": None},
                headers=headers,
            )
            response.raise_for_status()
            results = response.json()

    if not results:
        raise ValueError(f"Could not geocode address: {address}")

    info = extract_municipio_from_nominatim(results[0])

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
