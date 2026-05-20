from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from geocoding.geocoder import (
    _attach_user_house_number,
    _extract_trailing_house_number,
    _photon_feature_to_resolved,
    _photon_label,
    _strip_postal_prefixes,
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


# ── Query sanitization (Joaquin types "cp 28043" → Photon returns 0) ────


def test_strip_postal_prefixes_handles_cp_variants():
    # New contract: the CP prefix AND the digits are both stripped, and the
    # captured CP is returned for downstream ranking. Photon never sees the
    # `cp` token (it can't match it) nor the digits (they don't belong in
    # the street query).
    assert _strip_postal_prefixes("dr zamenhof cp 28043") == ("dr zamenhof", "28043")
    assert _strip_postal_prefixes("dr zamenhof CP 28043") == ("dr zamenhof", "28043")
    assert _strip_postal_prefixes("dr zamenhof c.p. 28043") == ("dr zamenhof", "28043")
    assert _strip_postal_prefixes("dr zamenhof c.p 28043") == ("dr zamenhof", "28043")


def test_strip_postal_prefixes_captures_typo_4digit_cp():
    # User dropped a digit: "cp 2027" instead of "28027". Treat as CP (not as
    # portal 2027) so the trailing-portal extractor doesn't get confused.
    cleaned, cp = _strip_postal_prefixes("matias turrion cp 2027")
    assert cleaned == "matias turrion"
    assert cp == "2027"


def test_strip_postal_prefixes_handles_codigo_postal_phrase():
    assert _strip_postal_prefixes("calle mayor 12 código postal 28013") == (
        "calle mayor 12",
        "28013",
    )
    assert _strip_postal_prefixes("calle mayor 12 codigo postal 28013") == (
        "calle mayor 12",
        "28013",
    )


def test_strip_postal_prefixes_leaves_other_queries_alone():
    assert _strip_postal_prefixes("calle mayor 12") == ("calle mayor 12", None)
    assert _strip_postal_prefixes("matias turrion") == ("matias turrion", None)


# ── Trailing house-number extraction ────────────────────────────────────


def test_extract_trailing_house_number_basic():
    assert _extract_trailing_house_number("matias turrion 12") == "12"
    assert _extract_trailing_house_number("calle mayor 8") == "8"
    assert _extract_trailing_house_number("gran via 102") == "102"


def test_extract_trailing_house_number_with_letter_suffix():
    assert _extract_trailing_house_number("calle mayor 12B") == "12B"


def test_extract_trailing_house_number_skips_cp():
    # "matias turrion cp 28027" → after CP strip: "matias turrion 28027" → no portal
    assert _extract_trailing_house_number("matias turrion cp 28027") is None
    # "matias turrion 12 cp 28027" → portal 12, CP 28027 trailing
    assert _extract_trailing_house_number("matias turrion 12 cp 28027") == "12"
    # "matias turrion 12 28027" (no cp keyword, just both numbers) → portal 12
    assert _extract_trailing_house_number("matias turrion 12 28027") == "12"


def test_extract_trailing_house_number_returns_none_when_missing():
    assert _extract_trailing_house_number("matias turrion") is None
    assert _extract_trailing_house_number("doctor zamenhof") is None


def test_extract_trailing_house_number_only_looks_at_end():
    # "Calle 12 de Octubre 8" — the trailing "8" wins, not the "12" in the name.
    assert _extract_trailing_house_number("calle 12 de octubre 8") == "8"
    # If only a number in the middle, we don't grab it.
    assert _extract_trailing_house_number("calle 12 de octubre") is None


# ── _attach_user_house_number ───────────────────────────────────────────


def _street_suggestion(label: str, road: str) -> ResolvedAddress:
    return ResolvedAddress(
        label=label,
        lat=40.46,
        lon=-3.66,
        municipality="Madrid",
        province="Comunidad de Madrid",
        road=road,
        house_number=None,
        country="España",
        provider="photon",
    )


def test_attach_user_house_number_fills_in_when_missing():
    sugg = _street_suggestion(
        label="Calle Matías Turrión, Hortaleza, Madrid",
        road="Calle Matías Turrión",
    )
    out = _attach_user_house_number([sugg], "12")
    assert len(out) == 1
    assert out[0].house_number == "12"
    assert "Calle Matías Turrión 12" in out[0].label
    assert "Hortaleza" in out[0].label


def test_attach_user_house_number_no_op_when_already_present():
    sugg = ResolvedAddress(
        label="Calle Mayor 8, Madrid",
        lat=40.4,
        lon=-3.7,
        municipality="Madrid",
        road="Calle Mayor",
        house_number="8",
        country="España",
        provider="photon",
    )
    out = _attach_user_house_number([sugg], "12")
    # Pre-existing house number wins — never overwrite real upstream data.
    assert out[0].house_number == "8"
    assert "Calle Mayor 8" in out[0].label


def test_attach_user_house_number_skips_when_no_road():
    sugg = ResolvedAddress(
        label="Madrid, Comunidad de Madrid",
        lat=40.4,
        lon=-3.7,
        municipality="Madrid",
        road=None,
        country="España",
        provider="photon",
    )
    out = _attach_user_house_number([sugg], "12")
    # City-level match: a portal makes no sense, leave it untouched.
    assert out[0].house_number is None
    assert "12" not in out[0].label


def test_attach_user_house_number_handles_none_number():
    sugg = _street_suggestion("Calle Mayor, Madrid", "Calle Mayor")
    out = _attach_user_house_number([sugg], None)
    assert out[0].house_number is None
    assert out[0].label == "Calle Mayor, Madrid"


# ── _photon_feature_to_resolved: street-level matches populate `road` ───
#
# Regression for the second iteration of Joaquin's report: even after the
# label/sanitization fixes, the autocomplete row showed "Calle Matías
# Turrión, Ciudad Lineal…" without a portal. Root cause: Photon's
# street-level features (`type == "street"`) expose the street name in
# `name` rather than `street`, but the resolver only read `street`. Result:
# `ResolvedAddress.road` was `None`, so `_attach_user_house_number` skipped
# the suggestion (its guard requires `road`), and the frontend never
# received a `house_number`, leaving "Continuar" disabled.


def test_photon_feature_to_resolved_street_level_populates_road():
    """Photon street-level features carry the street name in `name`.

    Without this, `_attach_user_house_number` can't inject the user's
    typed portal and the click never produces a usable Catastro query.
    """
    feature = {
        "geometry": {"type": "Point", "coordinates": [-3.6587841, 40.4586466]},
        "properties": {
            "osm_type": "W",
            "osm_id": 26114385,
            "osm_key": "highway",
            "osm_value": "residential",
            "type": "street",
            "name": "Calle Matías Turrión",
            "locality": "Colina",
            "district": "Ciudad Lineal",
            "city": "Madrid",
            "state": "Comunidad de Madrid",
            "country": "España",
            "postcode": "28016",
        },
    }
    resolved = _photon_feature_to_resolved(feature)
    assert resolved is not None
    assert resolved.road == "Calle Matías Turrión"
    assert resolved.house_number is None
    assert resolved.city_district == "Ciudad Lineal"


def test_photon_feature_to_resolved_portal_level_keeps_street_field():
    """Portal-level features expose `street` separately from `name`; that
    case must keep working — only the street-level branch was broken."""
    feature = {
        "geometry": {"type": "Point", "coordinates": [-3.7, 40.4]},
        "properties": {
            "osm_type": "N",
            "osm_id": 1,
            "type": "house",
            "name": "Some Building Name",
            "street": "Calle Mayor",
            "housenumber": "12",
            "city": "Madrid",
            "country": "España",
        },
    }
    resolved = _photon_feature_to_resolved(feature)
    assert resolved is not None
    assert resolved.road == "Calle Mayor"
    assert resolved.house_number == "12"


def test_photon_feature_to_resolved_does_not_use_name_for_non_street_types():
    """Cities, regions, POIs etc. share the `name` field too — we must NOT
    promote those to `road`, otherwise city-level matches would falsely
    accept synthesized portals from `_attach_user_house_number`."""
    feature = {
        "geometry": {"type": "Point", "coordinates": [-3.7, 40.4]},
        "properties": {
            "osm_type": "R",
            "osm_id": 2,
            "type": "city",
            "name": "Madrid",
            "city": "Madrid",
            "country": "España",
        },
    }
    resolved = _photon_feature_to_resolved(feature)
    assert resolved is not None
    assert resolved.road is None
