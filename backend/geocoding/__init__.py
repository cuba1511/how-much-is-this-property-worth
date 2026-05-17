"""Geocoding via Nominatim (OpenStreetMap)."""

from geocoding.geocoder import (
    get_municipio_from_address,
    municipio_from_resolved_address,
    reverse_geocode,
    suggest_addresses,
)

__all__ = [
    "get_municipio_from_address",
    "municipio_from_resolved_address",
    "reverse_geocode",
    "suggest_addresses",
]
