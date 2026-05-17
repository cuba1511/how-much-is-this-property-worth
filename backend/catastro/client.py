"""Catastro OVCCallejero client — Consulta_DNPLOC (units at a street number)."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
import httpx

from catastro.normalize import CatastroQuery, address_to_catastro_query
from models import CadastralUnit, ResolvedAddress

logger = logging.getLogger(__name__)

CATASTRO_NS = "http://www.catastro.meh.es/"
DNPLOC_URL = (
    "https://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/"
    "OVCCallejero.asmx/Consulta_DNPLOC"
)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _text(element: ET.Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    value = element.text.strip()
    return value or None


def _child(parent: ET.Element, name: str) -> ET.Element | None:
    for child in parent:
        if _local_name(child.tag) == name:
            return child
    return None


def _cadastral_reference(rc_node: ET.Element) -> str:
    parts = []
    for key in ("pc1", "pc2", "car", "cc1", "cc2"):
        parts.append(_text(_child(rc_node, key)) or "")
    return "".join(parts)


def _format_floor(floor: str | None) -> str | None:
    if floor is None:
        return None
    if floor == "-1":
        return "Sótano"
    if floor == "00":
        return "Bajo"
    if floor.isdigit():
        return str(int(floor))
    return floor


def _unit_label(
    *,
    block: str | None,
    staircase: str | None,
    floor: str | None,
    door: str | None,
) -> str:
    parts: list[str] = []
    if block:
        parts.append(f"Bloque {block}")
    if staircase:
        parts.append(f"Esc. {staircase}")
    floor_display = _format_floor(floor)
    if floor_display is not None:
        parts.append(f"Planta {floor_display}")
    if door:
        parts.append(f"Puerta {door}")
    return " · ".join(parts) if parts else "Inmueble"


def _parse_catastro_errors(root: ET.Element) -> None:
    """Raise when Catastro returns lerr (e.g. cod 33 LA VÍA NO EXISTE)."""
    for node in root.iter():
        if _local_name(node.tag) != "err":
            continue
        code = _text(_child(node, "cod"))
        description = _text(_child(node, "des")) or "Error de Catastro"
        if code or description:
            raise ValueError(f"{code} {description}".strip())


def _parse_units_xml(payload: str) -> list[CadastralUnit]:
    root = ET.fromstring(payload)
    _parse_catastro_errors(root)
    units: list[CadastralUnit] = []

    for node in root.iter():
        if _local_name(node.tag) != "rcdnp":
            continue

        rc_node = _child(node, "rc")
        if rc_node is None:
            continue

        cadastral_reference = _cadastral_reference(rc_node)
        if not cadastral_reference:
            continue

        block = staircase = floor = door = None
        dt_node = _child(node, "dt")
        if dt_node is not None:
            loint = None
            for desc in dt_node.iter():
                if _local_name(desc.tag) == "loint":
                    loint = desc
                    break
            if loint is not None:
                block = _text(_child(loint, "bl"))
                staircase = _text(_child(loint, "es"))
                floor = _text(_child(loint, "pt"))
                door = _text(_child(loint, "pu"))

        units.append(
            CadastralUnit(
                cadastral_reference=cadastral_reference,
                block=block or None,
                staircase=staircase or None,
                floor=floor,
                door=door,
                label=_unit_label(
                    block=block,
                    staircase=staircase,
                    floor=floor,
                    door=door,
                ),
            )
        )

    return units


async def fetch_units_by_street(
    *,
    province: str,
    municipality: str,
    road_type: str,
    road: str,
    number: str,
) -> list[CadastralUnit]:
    params: dict[str, str] = {
        "Provincia": province,
        "Municipio": municipality,
        "Sigla": road_type,
        "Calle": road,
        "Numero": number,
        # Catastro requires these keys even when empty.
        "Bloque": "",
        "Escalera": "",
        "Planta": "",
        "Puerta": "",
    }

    async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
        response = await client.get(DNPLOC_URL, params=params)
        response.raise_for_status()
        body = response.text

    if body.startswith("<?xml"):
        units = _parse_units_xml(body)
        logger.info(
            "Catastro DNPLOC %s %s %s %s → %d units",
            province,
            municipality,
            road,
            number,
            len(units),
        )
        return units

    raise ValueError(f"Unexpected Catastro response: {body[:200]}")


async def fetch_units_by_address(address: ResolvedAddress) -> list[CadastralUnit]:
    query: CatastroQuery = address_to_catastro_query(address)
    return await fetch_units_by_street(
        province=query.province,
        municipality=query.municipality,
        road_type=query.road_type,
        road=query.road,
        number=query.number,
    )
