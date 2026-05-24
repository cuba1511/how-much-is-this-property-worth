from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from main import (  # noqa: E402
    _build_coach_mock_valuation,
    _geocode_catastro_address,
    _normalize_airtable_address_for_valuation,
    _valuation_request_from_transaction,
)
from catastro.client import CatastroByRCResult, CatastroPropertyAddress  # noqa: E402
from models import MunicipioInfo, ResolvedAddress, TransactionDetail, ValuationRequest  # noqa: E402


@pytest.mark.parametrize("unit_suffix", ["1º-DR", "2º-DR"])
def test_normalize_airtable_address_strips_floor_door_suffix(unit_suffix: str):
    assert (
        _normalize_airtable_address_for_valuation(
            f"C. Cinco de Marzo, 3, {unit_suffix}, Casetas"
        )
        == "Calle Cinco de Marzo, 3, Casetas, España"
    )


def test_normalize_airtable_address_keeps_portal_number():
    assert (
        _normalize_airtable_address_for_valuation("Avda. Diagonal, 12, Barcelona")
        == "Avenida Diagonal, 12, Barcelona, España"
    )


def test_valuation_request_from_transaction_uses_normalized_address():
    transaction = TransactionDetail(
        id="rec123",
        transaction_name="Client - C. Cinco de Marzo, 3, 2º-DR, Casetas",
        address="C. Cinco de Marzo, 3, 2º-DR, Casetas",
        type="Piso",
        bedrooms=3,
        bathrooms=1,
        landsize_m2=90,
    )

    request = asyncio.run(_valuation_request_from_transaction(transaction))

    assert request.address == "Calle Cinco de Marzo, 3, Casetas, España"
    assert request.m2 == 90
    assert request.bedrooms == 3
    assert request.bathrooms == 1
    assert request.valuation_intent == "info"


def test_geocode_catastro_address_strips_local_suffix(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, str] = {}

    async def fake_get_municipio_from_address(query: str) -> MunicipioInfo:
        captured["query"] = query
        return MunicipioInfo(
            name="Zaragoza",
            slug="zaragoza",
            province="Zaragoza",
            lat=41.721783,
            lon=-1.029047,
            road="Calle Cinco de Marzo",
            postcode="50620",
        )

    monkeypatch.setattr("main.get_municipio_from_address", fake_get_municipio_from_address)
    result = CatastroByRCResult(
        reference="4009204XM6240G0006OB",
        is_parcel=False,
        units=[],
        address=CatastroPropertyAddress(
            province="ZARAGOZA",
            municipality="ZARAGOZA",
            road_type="CL",
            road="CINCO DE MARZO (CST)",
            number="3",
            postcode="50620",
            label="Calle CINCO DE MARZO (CST) 3, 50620, ZARAGOZA",
        ),
    )

    resolved = asyncio.run(_geocode_catastro_address(result))

    assert captured["query"] == "CINCO DE MARZO, 3, ZARAGOZA, 50620"
    assert resolved is not None
    assert resolved.municipality == "Zaragoza"
    assert resolved.road == "Calle Cinco de Marzo"


def test_build_coach_mock_valuation_returns_full_response():
    request = ValuationRequest(
        address="Calle Cinco de Marzo, 3, Casetas, España",
        m2=90,
        bedrooms=3,
        bathrooms=1,
        selected_address=ResolvedAddress(
            label="CINCO DE MARZO, 3, ZARAGOZA, 50620",
            lat=41.721783,
            lon=-1.029047,
            municipality="Zaragoza",
            province="ZARAGOZA",
            road="Calle Cinco de Marzo",
            provider="catastro",
        ),
        valuation_intent="info",
    )

    valuation = asyncio.run(_build_coach_mock_valuation(request))

    assert valuation.municipio.name == "Zaragoza"
    assert valuation.search_metadata.strategy == "coach_mock"
    assert valuation.stats.estimated_value is not None
    assert len(valuation.listings) > 0
    assert valuation.market_transactions is not None
    assert valuation.dataset is not None
    assert valuation.dataset.row_count == len(valuation.listings)
