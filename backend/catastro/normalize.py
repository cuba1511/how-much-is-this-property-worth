"""Map geocoded addresses (OSM/Photon) to Catastro Consulta_DNPLOC query fields."""

from __future__ import annotations

import re
import unicodedata

from models import ResolvedAddress

# Prefix (Spanish) → Catastro Sigla (Anexo I abreviaturas)
_ROAD_PREFIX_TO_SIGLA: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^calle\b", re.I), "CL"),
    (re.compile(r"^avenida\b", re.I), "AV"),
    (re.compile(r"^avda\.?\b", re.I), "AV"),
    (re.compile(r"^av\.?\b", re.I), "AV"),
    (re.compile(r"^paseo\b", re.I), "PS"),
    (re.compile(r"^plaza\b", re.I), "PZ"),
    (re.compile(r"^pl\.?\b", re.I), "PZ"),
    (re.compile(r"^camino\b", re.I), "CM"),
    (re.compile(r"^carretera\b", re.I), "CR"),
    (re.compile(r"^ronda\b", re.I), "RD"),
    (re.compile(r"^traves[ií]a\b", re.I), "TR"),
    (re.compile(r"^c\.\b", re.I), "CL"),
]


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _catastro_token(value: str) -> str:
    """Uppercase ASCII token as expected by the Catastro callejero."""
    return _strip_accents(value).upper().strip()


def _split_road(road: str) -> tuple[str, str]:
    """
    Returns (sigla, street_name) from a free-text road like 'Calle Ponciano'.
    Defaults to CL when no known prefix is found.
    """
    text = road.strip()
    for pattern, sigla in _ROAD_PREFIX_TO_SIGLA:
        match = pattern.match(text)
        if match:
            name = text[match.end() :].strip(" ,.")
            return sigla, _catastro_token(name)
    return "CL", _catastro_token(text)


def _normalize_municipality(address: ResolvedAddress) -> str:
    municipality = (address.municipality or "").strip()
    # Photon sometimes returns the autonomous community instead of the city.
    if re.search(r"comunidad|provincia|autonoma|autónoma", municipality, re.I):
        if address.city_district:
            return _catastro_token(address.city_district)
        if address.neighbourhood:
            return _catastro_token(address.neighbourhood)
        # "Madrid, Comunidad de Madrid" style labels → first segment
        head = address.label.split(",")[0].strip()
        if head:
            return _catastro_token(head)
    return _catastro_token(municipality)


def _normalize_province(address: ResolvedAddress, municipality_token: str) -> str:
    if address.province:
        province = address.province
        if re.search(r"comunidad", province, re.I):
            return municipality_token
        return _catastro_token(province)
    return municipality_token


class CatastroQuery(dict):
    """Typed dict-like query: province, municipality, road_type, road, number."""

    @property
    def province(self) -> str:
        return self["province"]

    @property
    def municipality(self) -> str:
        return self["municipality"]

    @property
    def road_type(self) -> str:
        return self["road_type"]

    @property
    def road(self) -> str:
        return self["road"]

    @property
    def number(self) -> str:
        return self["number"]


def address_to_catastro_query(address: ResolvedAddress) -> CatastroQuery:
    if not address.road:
        raise ValueError("Address has no street name (road)")
    if not address.house_number:
        raise ValueError("Address has no street number (house_number)")

    road_type, road_name = _split_road(address.road)
    municipality = _normalize_municipality(address)
    province = _normalize_province(address, municipality)

    number = re.sub(r"\D.*", "", str(address.house_number).strip()) or str(
        address.house_number
    ).strip()
    if not number:
        raise ValueError("Could not parse street number for Catastro lookup")

    return CatastroQuery(
        province=province,
        municipality=municipality,
        road_type=road_type,
        road=road_name,
        number=number,
    )
