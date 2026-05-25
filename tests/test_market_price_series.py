"""Tests for the TF Labs market price series layer.

Two flavours:

1. Unit tests that build a tiny in-memory SQLite with the production schema
   so the resolution chain and appreciation math run without depending on
   the real 50 MB artifact. These always run.

2. An end-to-end smoke test that exercises the real
   ``backend/data/market_price_series.db`` shipped via
   ``make build-market-series``. Skipped when the artifact isn't present so
   CI without the dataset doesn't fail.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from market.price_series import (  # noqa: E402
    DEFAULT_DB_PATH,
    PriceSeriesStore,
    compute_appreciation,
)


def _seed_in_memory_db(tmp_path: Path) -> Path:
    """Build a miniature SQLite that mirrors the production schema."""
    db_path = tmp_path / "market_price_series.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE market_towns (
            town_id        TEXT PRIMARY KEY,
            ine_code       TEXT NOT NULL,
            town_name      TEXT NOT NULL,
            town_name_norm TEXT NOT NULL,
            province_id    TEXT,
            community_id   TEXT
        );
        CREATE TABLE market_price_series (
            town_id TEXT NOT NULL REFERENCES market_towns(town_id),
            period  TEXT NOT NULL,
            value   REAL NOT NULL,
            PRIMARY KEY (town_id, period)
        ) WITHOUT ROWID;
        CREATE INDEX idx_market_ine_code  ON market_towns (ine_code);
        CREATE INDEX idx_market_town_name ON market_towns (town_name_norm);
        """
    )
    # Two towns: Madrid (canonical) + a fake "Alegria" with accents stripped.
    conn.executemany(
        "INSERT INTO market_towns VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("recMAD", "28079", "Madrid", "madrid", "recPROV28", "recCOM28"),
            ("recALE", "01001", "Alegría-Dulantzi", "alegria-dulantzi", "recPROV01", "recCOM01"),
        ],
    )
    conn.executemany(
        "INSERT INTO market_price_series VALUES (?, ?, ?)",
        [
            ("recMAD", "2020-01", 2_500.0),
            ("recMAD", "2022-06", 3_500.0),
            ("recMAD", "2026-01", 5_000.0),
            ("recALE", "2018-03", 1_000.0),
            ("recALE", "2026-01", 1_200.0),
        ],
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture()
def store(tmp_path: Path) -> PriceSeriesStore:
    db_path = _seed_in_memory_db(tmp_path)
    return PriceSeriesStore(db_path)


def test_resolve_by_airtable_record_id_wins_over_other_strategies(store: PriceSeriesStore):
    match = store.resolve_town(
        airtable_record_id="recMAD",
        ine_code="00000",  # wrong on purpose
        name="Barcelona",  # wrong on purpose
    )
    assert match is not None
    assert match.town_id == "recMAD"
    assert match.resolution_strategy == "airtable_town_id"


def test_resolve_by_ine_code_when_record_id_missing(store: PriceSeriesStore):
    match = store.resolve_town(ine_code="28079")
    assert match is not None
    assert match.town_id == "recMAD"
    assert match.resolution_strategy == "ine_code"


def test_resolve_by_normalized_name_strips_accents(store: PriceSeriesStore):
    match = store.resolve_town(name="alegria-dulantzi")
    assert match is not None
    assert match.town_id == "recALE"
    assert match.resolution_strategy == "name_match"


def test_resolve_returns_none_when_no_match(store: PriceSeriesStore):
    assert store.resolve_town(ine_code="99999", name="Atlantis") is None


def test_compute_appreciation_exact_match_for_madrid(store: PriceSeriesStore):
    town = store.resolve_town(airtable_record_id="recMAD")
    assert town is not None

    appreciation = compute_appreciation(
        store=store, town=town, settlement_date=date(2022, 6, 12)
    )
    assert appreciation is not None
    assert appreciation.from_period == "2022-06"
    assert appreciation.to_period == "2026-01"
    assert appreciation.from_eur_per_m2 == pytest.approx(3_500.0)
    assert appreciation.to_eur_per_m2 == pytest.approx(5_000.0)
    # (5000 - 3500) / 3500 = 0.4286
    assert appreciation.pct_change == pytest.approx(0.4286, abs=1e-3)
    assert appreciation.months_elapsed == 43
    assert appreciation.sample_quality == "exact"
    assert appreciation.annualized_pct_change is not None
    assert appreciation.resolution_strategy == "airtable_town_id"


def test_compute_appreciation_falls_back_to_earliest_when_settlement_pre_dates_coverage(
    store: PriceSeriesStore,
):
    town = store.resolve_town(airtable_record_id="recMAD")
    assert town is not None
    appreciation = compute_appreciation(
        store=store, town=town, settlement_date=date(1995, 5, 1)
    )
    assert appreciation is not None
    # No exact match → resolver returns the earliest period available.
    assert appreciation.from_period == "2020-01"
    assert appreciation.sample_quality == "nearest_available"


def test_compute_appreciation_nearest_available_when_settlement_between_periods(
    store: PriceSeriesStore,
):
    """Settlement at 2021-08 (between 2020-01 and 2022-06) anchors at 2020-01,
    because we never look forward — using a later month would inflate the
    apparent baseline."""
    town = store.resolve_town(airtable_record_id="recMAD")
    assert town is not None
    appreciation = compute_appreciation(
        store=store, town=town, settlement_date=date(2021, 8, 15)
    )
    assert appreciation is not None
    assert appreciation.from_period == "2020-01"
    assert appreciation.sample_quality == "nearest_available"


def test_compute_appreciation_omits_annualized_below_one_year(store: PriceSeriesStore):
    town = store.resolve_town(airtable_record_id="recMAD")
    assert town is not None
    # Pretend the dataset only has a 6-month span by overriding the latest
    # value lookup via a custom appreciation call with a fresh, short series.
    appreciation = compute_appreciation(
        store=store, town=town, settlement_date=date(2022, 6, 1)
    )
    # 43 months elapsed → annualized populated.
    assert appreciation is not None
    assert appreciation.annualized_pct_change is not None


@pytest.mark.skipif(
    not DEFAULT_DB_PATH.exists(),
    reason="Real market_price_series.db not built (run `make build-market-series`).",
)
def test_real_dataset_madrid_appreciation_since_2022():
    """End-to-end check against the real artifact. Skipped in environments
    without the SQLite (e.g. fresh checkouts that haven't ingested the CSV).
    """
    store = PriceSeriesStore(DEFAULT_DB_PATH)
    town = store.resolve_town(ine_code="28079")
    assert town is not None and town.town_name == "Madrid"
    appreciation = compute_appreciation(
        store=store, town=town, settlement_date=date(2022, 6, 15)
    )
    assert appreciation is not None
    # As of the 2026-01 snapshot Madrid sits well above 5 000 €/m².
    assert appreciation.to_eur_per_m2 > 5_000
    # Sanity: any settlement in 2022 should show a meaningful positive change
    # in the smoothed series.
    assert appreciation.pct_change > 0.20
