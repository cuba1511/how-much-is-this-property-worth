"""
Tests for the Spanish Catastro Consulta_DNPLOC integration.

DNPLOC = "Datos NO Protegidos por Localización" — public web service that lists
all registered units (escalera/planta/puerta + referencia catastral) at a
street number. Official docs:
https://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/OVCCallejero.asmx?op=Consulta_DNPLOC
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

# Run as `pytest tests/test_catastro.py` from repo root; backend modules live in backend/
BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from catastro.client import _parse_units_xml, fetch_units_by_street  # noqa: E402
from catastro.normalize import address_to_catastro_query  # noqa: E402
from models import ResolvedAddress  # noqa: E402

# Minimal XML fragment shaped like a real Catastro response (2 units).
SAMPLE_XML = """<?xml version="1.0" encoding="utf-8"?>
<consulta_dnp xmlns="http://www.catastro.meh.es/">
  <lrcdnp>
    <rcdnp>
      <rc><pc1>9854702</pc1><pc2>VK3795D</pc2><car>0003</car><cc1>Z</cc1><cc2>T</cc2></rc>
      <dt><locs><lous><lourb><loint><es>1</es><pt>00</pt><pu>A</pu></loint></lourb></lous></locs></dt>
    </rcdnp>
    <rcdnp>
      <rc><pc1>9854702</pc1><pc2>VK3795D</pc2><car>0006</car><cc1>Q</cc1><cc2>I</cc2></rc>
      <dt><locs><lous><lourb><loint><es>1</es><pt>01</pt><pu>A</pu></loint></lourb></lous></locs></dt>
    </rcdnp>
  </lrcdnp>
</consulta_dnp>
"""


def test_parse_units_xml_extracts_reference_and_location():
    units = _parse_units_xml(SAMPLE_XML)
    assert len(units) == 2
    assert units[0].cadastral_reference == "9854702VK3795D0003ZT"
    assert units[0].staircase == "1"
    assert units[0].floor == "00"
    assert units[0].door == "A"
    assert "Puerta A" in units[0].label


def test_address_to_catastro_query_splits_street():
    addr = ResolvedAddress(
        label="Calle Ponciano, 7, Madrid",
        lat=40.42,
        lon=-3.70,
        municipality="Madrid",
        province="Madrid",
        road="Calle Ponciano",
        house_number="7",
        provider="test",
    )
    q = address_to_catastro_query(addr)
    assert q["road_type"] == "CL"
    assert q["road"] == "PONCIANO"
    assert q["number"] == "7"
    assert q["municipality"] == "MADRID"


def test_api_catastro_units_endpoint():
    """FastAPI route is registered and returns JSON (in-process, no live server)."""
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    response = client.get(
        "/api/catastro/units",
        params={
            "province": "MADRID",
            "municipality": "MADRID",
            "road": "PONCIANO",
            "number": "7",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 10
    assert "cadastral_reference" in data[0]
    assert "label" in data[0]


@pytest.mark.integration
def test_live_catastro_ponciano_7_madrid():
    """Hits the real Catastro API — requires network."""
    units = asyncio.run(
        fetch_units_by_street(
            province="MADRID",
            municipality="MADRID",
            road_type="CL",
            road="PONCIANO",
            number="7",
        )
    )
    assert len(units) >= 10
    refs = {u.cadastral_reference for u in units}
    assert len(refs) == len(units)
    # Known unit from manual verification (Planta 00, Puerta A)
    assert any(u.floor == "00" and u.door == "A" for u in units)
