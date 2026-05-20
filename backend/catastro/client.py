"""Catastro OVCCallejero client.

Two read flows we use:
 - Consulta_DNPLOC: list units (escalera/planta/puerta) at a street number.
   Driven by the geocoded address (province, municipality, road, number).
 - Consulta_DNPRC: resolve a property directly from its cadastral reference.
   Accepts a 14-char parcel ref (returns all units in the parcel) OR a
   20-char unit ref (returns a single inmueble with full address). Used by
   the "I know my catastro" alternative entry point in the UI.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

import httpx

from catastro.normalize import CatastroQuery, address_to_catastro_query
from models import CadastralUnit, ResolvedAddress

logger = logging.getLogger(__name__)

CATASTRO_NS = "http://www.catastro.meh.es/"
DNPLOC_URL = (
    "https://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/"
    "OVCCallejero.asmx/Consulta_DNPLOC"
)
DNPRC_URL = (
    "https://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/"
    "OVCCallejero.asmx/Consulta_DNPRC"
)


# Road-type abbreviations Catastro returns in <tv> (Anexo I). We expand a
# small subset back to the long Spanish name so the address label we build
# from the DNPRC response reads naturally ("CALLE DOCTOR ZAMENHOF 8" rather
# than "CL DOCTOR ZAMENHOF 8"). Anything we don't recognise falls back to
# the raw token so we never silently drop information.
_ROAD_TYPE_EXPANSIONS: dict[str, str] = {
    "CL": "Calle",
    "AV": "Avenida",
    "PS": "Paseo",
    "PZ": "Plaza",
    "CM": "Camino",
    "CR": "Carretera",
    "RD": "Ronda",
    "TR": "Travesía",
    "GL": "Glorieta",
    "BO": "Barrio",
    "UR": "Urbanización",
}


@dataclass(frozen=True)
class CatastroPropertyAddress:
    """Address fields extracted from a Catastro DNPRC response.

    These are normalized enough to feed into geocoding (Nominatim/Photon) so
    the resulting `ResolvedAddress` carries lat/lon for the valuation pipeline.
    """

    province: str
    municipality: str
    road_type: Optional[str]
    road: Optional[str]
    number: Optional[str]
    postcode: Optional[str]
    label: str


@dataclass(frozen=True)
class CatastroByRCResult:
    """Outcome of a Consulta_DNPRC lookup.

    `is_parcel` is True when the user supplied a 14-char parcel ref: in that
    case `units` lists every inmueble inside the parcel and the UI should
    show the same disambiguation step as the address flow.
    """

    reference: str
    is_parcel: bool
    units: list[CadastralUnit]
    address: Optional[CatastroPropertyAddress]


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


# ---------------------------------------------------------------------------
# Consulta_DNPRC — direct lookup by cadastral reference.
# ---------------------------------------------------------------------------


def normalize_cadastral_reference(raw: str) -> str:
    """Uppercase + strip spaces/dashes. Returns the user-typed RC ready to
    send to Catastro. Length must be 14 (parcela) or 20 (inmueble)."""
    if raw is None:
        raise ValueError("Referencia catastral vacía")
    cleaned = "".join(ch for ch in raw if not ch.isspace()).replace("-", "").upper()
    if not cleaned:
        raise ValueError("Referencia catastral vacía")
    if len(cleaned) not in (14, 20):
        raise ValueError(
            "La referencia catastral debe tener 14 dígitos (parcela) "
            "o 20 (inmueble)"
        )
    if not cleaned.isalnum():
        raise ValueError("La referencia catastral solo admite letras y números")
    return cleaned


def _read_loint(parent: ET.Element) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Walk down to <loint> wherever it sits and return (bl, es, pt, pu)."""
    for desc in parent.iter():
        if _local_name(desc.tag) != "loint":
            continue
        return (
            _text(_child(desc, "bl")),
            _text(_child(desc, "es")),
            _text(_child(desc, "pt")),
            _text(_child(desc, "pu")),
        )
    return None, None, None, None


def _read_dt_address(dt_node: ET.Element) -> CatastroPropertyAddress:
    """Extract the address pieces from a <dt> block (DNPRC or DNPLOC).

    Catastro nests addresses under <locs>/<lous>/<lourb>/<dir>, with the
    municipality + province as siblings of <locs>. We walk defensively so
    the parser doesn't break on minor schema drift between rural/urban
    responses."""
    province = _text(_child(dt_node, "np")) or ""
    municipality = _text(_child(dt_node, "nm")) or ""

    road_type = road = number = postcode = None
    for desc in dt_node.iter():
        name = _local_name(desc.tag)
        if name == "dir":
            road_type = _text(_child(desc, "tv"))
            road = _text(_child(desc, "nv"))
            number = _text(_child(desc, "pnp")) or number
        elif name == "dp":
            postcode = _text(desc)

    expanded_type = _ROAD_TYPE_EXPANSIONS.get((road_type or "").upper())
    label_parts: list[str] = []
    if road:
        if expanded_type:
            label_parts.append(f"{expanded_type} {road}")
        elif road_type:
            label_parts.append(f"{road_type} {road}")
        else:
            label_parts.append(road)
    if number:
        label_parts[-1] = f"{label_parts[-1]} {number}" if label_parts else number
    if postcode:
        label_parts.append(postcode)
    if municipality:
        label_parts.append(municipality)
    if province and province != municipality:
        label_parts.append(province)
    label = ", ".join(label_parts) if label_parts else (municipality or province or "")

    return CatastroPropertyAddress(
        province=province,
        municipality=municipality,
        road_type=road_type,
        road=road,
        number=number,
        postcode=postcode,
        label=label,
    )


def _unit_from_rcdnp(node: ET.Element) -> Optional[CadastralUnit]:
    """Build a CadastralUnit from an <rcdnp> node (used by both DNPLOC and
    DNPRC when the user gives a 14-char parcela)."""
    rc_node = _child(node, "rc")
    if rc_node is None:
        return None
    reference = _cadastral_reference(rc_node)
    if not reference:
        return None
    dt_node = _child(node, "dt")
    block = staircase = floor = door = None
    if dt_node is not None:
        block, staircase, floor, door = _read_loint(dt_node)
    return CadastralUnit(
        cadastral_reference=reference,
        block=block or None,
        staircase=staircase or None,
        floor=floor,
        door=door,
        label=_unit_label(block=block, staircase=staircase, floor=floor, door=door),
    )


def _parse_dnprc_xml(payload: str, *, requested_rc: str) -> CatastroByRCResult:
    """Parse Consulta_DNPRC. Handles both <bico> (20-char unit) and
    <lrcdnp> (14-char parcela) shapes in the same response document."""
    root = ET.fromstring(payload)
    _parse_catastro_errors(root)

    units: list[CadastralUnit] = []
    address: Optional[CatastroPropertyAddress] = None
    is_parcel = len(requested_rc) == 14

    # Unit-level response: <bico><bi>...
    bi_node: Optional[ET.Element] = None
    for desc in root.iter():
        if _local_name(desc.tag) == "bi":
            bi_node = desc
            break

    if bi_node is not None:
        rc_node: Optional[ET.Element] = None
        for desc in bi_node.iter():
            if _local_name(desc.tag) == "rc":
                rc_node = desc
                break
        cadastral_reference = (
            _cadastral_reference(rc_node) if rc_node is not None else requested_rc
        )

        block, staircase, floor, door = (None, None, None, None)
        dt_node = _child(bi_node, "dt")
        if dt_node is not None:
            address = _read_dt_address(dt_node)
            block, staircase, floor, door = _read_loint(dt_node)
        # Built area lives under <debi><sfc>.
        sfc_value: Optional[float] = None
        debi_node = _child(bi_node, "debi")
        if debi_node is not None:
            sfc_text = _text(_child(debi_node, "sfc"))
            try:
                sfc_value = float(sfc_text) if sfc_text else None
            except ValueError:
                sfc_value = None

        units.append(
            CadastralUnit(
                cadastral_reference=cadastral_reference,
                block=block or None,
                staircase=staircase or None,
                floor=floor,
                door=door,
                built_area_m2=sfc_value,
                label=_unit_label(block=block, staircase=staircase, floor=floor, door=door),
            )
        )

    # Parcela-level response: <lrcdnp><rcdnp>... (or DNPLOC-style shape).
    for desc in root.iter():
        if _local_name(desc.tag) != "rcdnp":
            continue
        unit = _unit_from_rcdnp(desc)
        if unit is None:
            continue
        units.append(unit)
        if address is None:
            dt_node = _child(desc, "dt")
            if dt_node is not None:
                address = _read_dt_address(dt_node)

    # Deduplicate by RC (parcela responses can repeat units across rcdnp entries).
    seen: set[str] = set()
    unique: list[CadastralUnit] = []
    for unit in units:
        if unit.cadastral_reference in seen:
            continue
        seen.add(unit.cadastral_reference)
        unique.append(unit)

    return CatastroByRCResult(
        reference=requested_rc,
        is_parcel=is_parcel or len(unique) > 1,
        units=unique,
        address=address,
    )


async def fetch_property_by_reference(reference: str) -> CatastroByRCResult:
    """Resolve a cadastral reference via Consulta_DNPRC.

    Raises `ValueError` on bad input or when Catastro returns an `<err>`
    descriptor (e.g. RC does not exist). Network failures bubble up as
    `httpx.HTTPError` so the FastAPI layer can map them to 502."""
    rc = normalize_cadastral_reference(reference)
    params = {"Provincia": "", "Municipio": "", "RC": rc}

    async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
        response = await client.get(DNPRC_URL, params=params)
        response.raise_for_status()
        body = response.text

    if not body.startswith("<?xml"):
        raise ValueError(f"Unexpected Catastro response: {body[:200]}")

    result = _parse_dnprc_xml(body, requested_rc=rc)
    logger.info(
        "Catastro DNPRC %s → %d units (parcel=%s, address=%s)",
        rc,
        len(result.units),
        result.is_parcel,
        result.address.label if result.address else "n/a",
    )
    if not result.units and result.address is None:
        raise ValueError("La referencia catastral no devolvió ningún inmueble")
    return result
