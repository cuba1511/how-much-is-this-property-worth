from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from geocoding.geocoder import (
    filter_spain_resolved_addresses,
    is_spain_coordinates,
    is_spain_country_name,
    is_spain_nominatim_result,
    is_spain_resolved_address,
)
from models import ResolvedAddress


def test_is_spain_country_name():
    assert is_spain_country_name("España")
    assert is_spain_country_name("Spain")
    assert not is_spain_country_name("France")


def test_is_spain_coordinates():
    assert is_spain_coordinates(40.4168, -3.7038)  # Madrid
    assert is_spain_coordinates(28.1, -15.4)  # Canarias
    assert not is_spain_coordinates(48.8566, 2.3522)  # Paris


def test_is_spain_nominatim_result():
    assert is_spain_nominatim_result(
        {"lat": "40.4", "lon": "-3.7", "address": {"country": "España"}}
    )
    assert not is_spain_nominatim_result(
        {"lat": "48.8", "lon": "2.3", "address": {"country": "France"}}
    )


def test_is_spain_resolved_address():
    madrid = ResolvedAddress(
        label="Calle Mayor, Madrid",
        lat=40.4168,
        lon=-3.7038,
        municipality="Madrid",
        country="España",
    )
    assert is_spain_resolved_address(madrid)

    paris = ResolvedAddress(
        label="Rue de Rivoli, Paris",
        lat=48.8566,
        lon=2.3522,
        municipality="Paris",
        country="France",
    )
    assert not is_spain_resolved_address(paris)


def test_filter_spain_resolved_addresses():
    madrid = ResolvedAddress(
        label="Madrid",
        lat=40.4,
        lon=-3.7,
        municipality="Madrid",
        country="España",
    )
    paris = ResolvedAddress(
        label="Paris",
        lat=48.8,
        lon=2.3,
        municipality="Paris",
        country="France",
    )
    filtered = filter_spain_resolved_addresses([madrid, paris])
    assert filtered == [madrid]
