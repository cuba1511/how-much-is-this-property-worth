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
    _build_no_scrape_valuation,
    _geocode_catastro_address,
    _normalize_airtable_address_for_valuation,
    _valuation_request_from_transaction,
)
from market.price_series import TownMatch  # noqa: E402
from airtable.client import AirtableConfig  # noqa: E402
from airtable.transactions import (  # noqa: E402
    VALUATION_FIELDS,
    _base_filter_formula,
    _build_search_formula,
    _summary_from_record,
    get_transaction_for_valuation,
)
from catastro.client import CatastroByRCResult, CatastroPropertyAddress  # noqa: E402
from models import MunicipioInfo, ResolvedAddress, TransactionDetail, ValuationRequest  # noqa: E402


@pytest.mark.parametrize("unit_suffix", ["0°-DR", "1º-DR", "2º-DR"])
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


def test_airtable_summary_maps_final_purchase_cost_fields():
    summary = _summary_from_record(
        {
            "id": "rec123",
            "fields": {
                "Transaction Name": "Client - Address",
                "Landsize": 100,
                "Price": 200_000,
                "Final reno cost": 30_000,
                "Final furniture cost": 8_000,
                "Technical project cost": 4_000,
                "Home appliances cost": 3_000,
                "Cleaning cost": 500,
                "Real estate agent fee": 6_000,
                "Land registry cost": 700,
                "PropHero fee": 10_000,
                "Notary cost": 900,
                "Insurance": 450,
                "Council rate": 600,
                "Service charges": 1_200,
                "Final Total Price (from Properties)": [265_000],
            },
        }
    )

    assert summary.price == 200_000
    assert summary.final_reno_cost == 30_000
    assert summary.final_furniture_cost == 8_000
    assert summary.technical_project_costs == 4_000
    assert summary.home_appliances_cost == 3_000
    assert summary.cleaning_cost == 500
    assert summary.real_estate_agent_fee == 6_000
    assert summary.land_registry_cost == 700
    assert summary.prophero_fee == 10_000
    assert summary.notary_cost == 900
    assert summary.insurance == 450
    assert summary.council_rate == 600
    assert summary.service_charges == 1_200
    assert summary.final_total_price == 265_000
    assert summary.purchase_eur_per_m2 == 2_650


def test_get_transaction_for_valuation_uses_projected_airtable_fields(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, list[str] | None] = {}

    async def fake_get_record(**kwargs):
        captured["fields"] = kwargs.get("fields")
        return {
            "id": "rec123",
            "fields": {
                "Transaction Name": "Client - Address",
                "Address": "Calle Test, 1, Valencia",
                "Beds": 2,
                "Baths": 1,
                "Landsize": 70,
            },
        }

    monkeypatch.setattr("airtable.transactions.get_record", fake_get_record)

    transaction = asyncio.run(
        get_transaction_for_valuation(
            config=AirtableConfig(pat="pat", base_id="app"),
            record_id="rec123",
        )
    )

    assert transaction.id == "rec123"
    assert captured["fields"] is not None
    assert set(VALUATION_FIELDS).issuperset(captured["fields"])
    assert "Transaction Name" in captured["fields"]
    assert "Address" in captured["fields"]


def test_coach_transaction_base_filter_targets_leased_spanish_properties():
    formula = _base_filter_formula()

    assert "{Country (from Properties)} = 'Spain'" in formula
    assert "{Stage} = 'Property leased'" in formula


def test_coach_transaction_search_keeps_base_filter():
    formula = _build_search_formula("casetas")

    assert "{Country (from Properties)} = 'Spain'" in formula
    assert "{Stage} = 'Property leased'" in formula
    assert "FIND('casetas', LOWER({Transaction Name}))" in formula


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


class _FakePriceSeriesStore:
    """Stub PriceSeriesStore for the no-scrape valuation test.

    Mirrors the two methods ``_build_no_scrape_valuation`` actually calls.
    Keeping it dumb (no SQLite) lets the test run in <10ms and avoids the
    ``backend/data/market_price_series.db`` dependency.
    """

    def __init__(self, *, town: TownMatch | None, eur_per_m2: float | None):
        self._town = town
        self._latest = ("2025-12", eur_per_m2) if eur_per_m2 is not None else None
        self.resolve_calls: list[dict] = []

    def resolve_town(self, **kwargs):
        self.resolve_calls.append(kwargs)
        return self._town

    def latest_value(self, town_id: str):
        return self._latest


def test_build_no_scrape_valuation_uses_market_series_anchor(
    monkeypatch: pytest.MonkeyPatch,
):
    """When the TF Labs town resolves, the headline value is €/m² × m² with
    method 'market_series' and no listings/regression."""
    town = TownMatch(
        town_id="town-zaragoza",
        ine_code="50297",
        town_name="Zaragoza",
        province_id="ZARAGOZA",
        community_id="AR",
        resolution_strategy="name_match",
    )
    store = _FakePriceSeriesStore(town=town, eur_per_m2=2_400.0)
    monkeypatch.setattr("main.get_default_store", lambda: store)

    request = ValuationRequest(
        address="Calle Cinco de Marzo, 3, Zaragoza, España",
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

    valuation = asyncio.run(_build_no_scrape_valuation(request))

    assert valuation.listings == []
    assert valuation.regression is None
    assert valuation.dataset is not None and valuation.dataset.row_count == 0
    assert valuation.search_metadata.strategy == "no_scrape"
    assert valuation.search_metadata.final_stage == "market_series"
    assert valuation.stats.estimation_method == "market_series"
    assert valuation.stats.confidence_method == "flat_pct"
    assert valuation.stats.avg_price_per_m2 == 2_400
    assert valuation.stats.estimated_value == 216_000  # 2400 × 90
    # ±10% band when there's no comparable σ to lean on.
    assert valuation.stats.price_range_low == int(216_000 * 0.90)
    assert valuation.stats.price_range_high == int(216_000 * 1.10)
    assert store.resolve_calls == [
        {
            "airtable_record_id": None,
            "name": "Zaragoza",
            "province_id": "ZARAGOZA",
        }
    ]


def test_build_no_scrape_valuation_degrades_without_price_series(
    monkeypatch: pytest.MonkeyPatch,
):
    """When TF Labs has no value for the town we still return a well-formed
    response, but with no estimated value — better to be honest than to
    invent a number."""
    monkeypatch.setattr("main.get_default_store", lambda: None)

    request = ValuationRequest(
        address="Calle Cinco de Marzo, 3, Zaragoza, España",
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

    valuation = asyncio.run(_build_no_scrape_valuation(request))

    assert valuation.stats.estimated_value is None
    assert valuation.stats.avg_price_per_m2 is None
    assert valuation.stats.estimation_method is None
    assert valuation.stats.confidence_method is None
    assert valuation.listings == []
    assert valuation.search_metadata.strategy == "no_scrape"
