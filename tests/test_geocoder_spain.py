from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from geocoding.geocoder import (
    _photon_label,
    _strip_postcode_from_label,
    build_address_label,
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


# ── Postcode stripping (tester feedback: "todos los CPs están mal") ─────


def test_strip_postcode_removes_5_digit_token():
    assert (
        _strip_postcode_from_label("Calle Mayor 12, 03001 Alicante, España")
        == "Calle Mayor 12, Alicante, España"
    )


def test_strip_postcode_trailing_segment():
    assert (
        _strip_postcode_from_label("Calle Mayor, 12, 03001, Alicante, España")
        == "Calle Mayor, 12, Alicante, España"
    )


def test_strip_postcode_leaves_house_number_untouched():
    # The 12 is the house number — must NOT be stripped because it's not 5 digits.
    label = "Calle Mayor 12, Alicante, España"
    assert _strip_postcode_from_label(label) == label


def test_strip_postcode_handles_no_postcode():
    label = "Calle Mayor, Alicante, España"
    assert _strip_postcode_from_label(label) == label


def test_photon_label_omits_postcode():
    props = {
        "street": "Calle Mayor",
        "housenumber": "12",
        "city": "Alicante",
        "state": "Comunidad Valenciana",
        "postcode": "03001",  # The supposedly-wrong one we no longer want to show.
        "country": "España",
    }
    label = _photon_label(props)
    assert "03001" not in label
    assert "Calle Mayor 12" in label
    assert "Alicante" in label


def test_photon_label_includes_district_for_disambiguation():
    """Same street name in two Madrid districts → district must appear in
    the label so the dropdown rows aren't identical (real case for Calle
    Matías Turrión, which exists in both Ciudad Lineal and Hortaleza)."""
    ciudad_lineal = {
        "street": "Calle Matías Turrión",
        "district": "Ciudad Lineal",
        "locality": "Colina",
        "city": "Madrid",
        "state": "Comunidad de Madrid",
        "postcode": "28016",
        "country": "España",
    }
    hortaleza = {
        "street": "Calle Matías Turrión",
        "district": "Hortaleza",
        "locality": "Canillas",
        "city": "Madrid",
        "state": "Comunidad de Madrid",
        "postcode": "28033",
        "country": "España",
    }
    label_a = _photon_label(ciudad_lineal)
    label_b = _photon_label(hortaleza)
    assert "Ciudad Lineal" in label_a
    assert "Hortaleza" in label_b
    assert label_a != label_b
    assert "28016" not in label_a
    assert "28033" not in label_b


def test_photon_label_falls_back_to_locality_when_no_district():
    props = {
        "street": "Calle Mayor",
        "locality": "Casco Antiguo",
        "city": "Alicante",
        "country": "España",
    }
    label = _photon_label(props)
    assert "Casco Antiguo" in label
    assert "Alicante" in label


def test_nominatim_label_omits_postcode():
    addr = {
        "road": "Calle Mayor",
        "house_number": "12",
        "city": "Alicante",
        "province": "Alicante",
        "postcode": "03001",
        "country": "España",
    }
    label = build_address_label(addr)
    assert "03001" not in label
    assert "Calle Mayor 12" in label


def test_nominatim_label_includes_city_district():
    """Nominatim's `city_district` is the equivalent of Photon's `district`
    for disambiguating same-named streets (e.g. Madrid)."""
    addr = {
        "road": "Calle Matías Turrión",
        "house_number": "7",
        "city_district": "Hortaleza",
        "city": "Madrid",
        "province": "Madrid",
        "country": "España",
    }
    label = build_address_label(addr)
    assert "Hortaleza" in label
    assert "Calle Matías Turrión 7" in label


def test_photon_label_hides_wrong_madrid_postcodes():
    """Regression test for Joaquin's report: OSM/Photon's street-level CPs
    don't match Correos' portal-level CPs for these Madrid addresses.
    Joaquin sees wrong CPs (28027 vs Photon 28016/28033 for Matías Turrión,
    28043 vs Photon 28037 for Dr. Zamenhof) — both come from real upstream
    feature properties, so the cure is to not show them at all."""
    matias_turrion = {
        "street": "Calle Matías Turrión",
        "district": "Hortaleza",
        "city": "Madrid",
        "state": "Comunidad de Madrid",
        "postcode": "28033",  # OSM-tagged; Joaquin expected 28027.
        "country": "España",
    }
    label = _photon_label(matias_turrion)
    assert "28033" not in label
    assert "28027" not in label
    assert "Calle Matías Turrión" in label
    assert "Madrid" in label

    zamenhof = {
        "street": "Calle Doctor Zamenhof",
        "district": "San Blas - Canillejas",
        "city": "Madrid",
        "state": "Comunidad de Madrid",
        "postcode": "28037",  # OSM-tagged; Joaquin expected 28043.
        "country": "España",
    }
    label = _photon_label(zamenhof)
    assert "28037" not in label
    assert "28043" not in label
    assert "Calle Doctor Zamenhof" in label
    assert "San Blas - Canillejas" in label
