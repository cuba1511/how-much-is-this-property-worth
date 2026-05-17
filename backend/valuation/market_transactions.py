import hashlib
import random
from datetime import date, timedelta
from statistics import mean
from typing import Optional

from models import (
    MarketTransaction,
    MarketTransactionChartPoint,
    MarketTransactions,
    MarketTransactionsSummary,
    MunicipioInfo,
)

DEFAULT_TRANSACTION_COUNT = 6


def _mean_int(values: list[int]) -> Optional[int]:
    return int(mean(values)) if values else None


def _round_pct(value: Optional[float]) -> Optional[float]:
    return round(value, 1) if value is not None else None


def _seed_for_market(
    address: str,
    municipio: MunicipioInfo,
    *,
    m2: int,
    bedrooms: int,
    bathrooms: int,
) -> int:
    seed_input = "|".join(
        [
            address or "",
            municipio.slug or municipio.name,
            str(m2),
            str(bedrooms),
            str(bathrooms),
        ]
    )
    return int(hashlib.sha256(seed_input.encode("utf-8")).hexdigest()[:12], 16)


def _fallback_price_per_m2(municipio: MunicipioInfo) -> int:
    province = (municipio.province or "").lower()
    city = (municipio.name or "").lower()

    if "madrid" in {province, city}:
        return 5_300
    if "barcelona" in {province, city}:
        return 5_600
    if "balears" in province or "ibiza" in city or "palma" in city:
        return 5_100
    if city in {"valencia", "malaga"} or province in {"valencia", "málaga", "malaga"}:
        return 3_700
    return 2_900


def _build_address_label(
    rng: random.Random,
    index: int,
    municipio: MunicipioInfo,
) -> str:
    anchors = [
        municipio.road,
        municipio.neighbourhood,
        municipio.quarter,
        municipio.city_district,
    ]
    cleaned_anchors = [value.strip() for value in anchors if value and value.strip()]

    if cleaned_anchors:
        anchor = cleaned_anchors[index % len(cleaned_anchors)]
        if "calle" not in anchor.lower():
            anchor = f"Calle {anchor}"
    else:
        anchor = f"Calle Mercado {index + 1}"

    return f"{anchor} {rng.randint(3, 97)}, {municipio.name}"


def _build_chart_series(transactions: list[MarketTransaction]) -> list[MarketTransactionChartPoint]:
    series: list[MarketTransactionChartPoint] = []
    for index, transaction in enumerate(transactions[:6], start=1):
        short_address = (transaction.address or f"Comp {index}").split(",")[0]
        series.append(
            MarketTransactionChartPoint(
                label=short_address if len(short_address) <= 18 else short_address[:15].rstrip() + "...",
                asking_price=transaction.asking_price,
                closing_price=transaction.closing_price,
                negotiation_margin_pct=transaction.negotiation_margin_pct,
            )
        )
    return series


def build_market_transactions_mock(
    address: str,
    municipio: MunicipioInfo,
    *,
    m2: int,
    bedrooms: int,
    bathrooms: int,
    listing_avg_price_per_m2: Optional[int] = None,
) -> MarketTransactions:
    rng = random.Random(
        _seed_for_market(
            address,
            municipio,
            m2=m2,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
        )
    )

    base_asking_price_per_m2 = listing_avg_price_per_m2 or _fallback_price_per_m2(municipio)
    transactions: list[MarketTransaction] = []
    today = date.today()

    for index in range(DEFAULT_TRANSACTION_COUNT):
        transaction_m2 = max(35, int(round(m2 * rng.uniform(0.9, 1.12))))
        transaction_bedrooms = max(0, bedrooms + rng.choice([-1, 0, 0, 1]))
        transaction_bathrooms = max(1, bathrooms + rng.choice([-1, 0, 0, 1]))
        asking_ppm2 = int(round(base_asking_price_per_m2 * rng.uniform(0.94, 1.07)))
        margin_pct = _round_pct(rng.uniform(3.5, 9.8)) or 0.0
        closing_ppm2 = int(round(asking_ppm2 * (1 - (margin_pct / 100))))
        asking_price = asking_ppm2 * transaction_m2
        closing_price = closing_ppm2 * transaction_m2
        days_since_close = rng.randint(18, 210)
        close_date = (today - timedelta(days=days_since_close)).isoformat()
        days_on_market = rng.randint(21, 96)

        transactions.append(
            MarketTransaction(
                id=f"txn-{municipio.slug}-{index + 1}",
                address=_build_address_label(rng, index, municipio),
                m2=transaction_m2,
                bedrooms=transaction_bedrooms,
                bathrooms=transaction_bathrooms,
                asking_price=asking_price,
                closing_price=closing_price,
                asking_price_per_m2=asking_ppm2,
                closing_price_per_m2=closing_ppm2,
                negotiation_margin_pct=margin_pct,
                close_date=close_date,
                days_on_market=days_on_market,
                source="market-mock",
                distance_m=rng.randint(120, 1400),
            )
        )

    asking_prices = [transaction.asking_price for transaction in transactions if transaction.asking_price]
    closing_prices = [transaction.closing_price for transaction in transactions if transaction.closing_price]
    asking_ppm2_values = [
        transaction.asking_price_per_m2 for transaction in transactions if transaction.asking_price_per_m2
    ]
    closing_ppm2_values = [
        transaction.closing_price_per_m2 for transaction in transactions if transaction.closing_price_per_m2
    ]
    margin_values = [
        transaction.negotiation_margin_pct for transaction in transactions if transaction.negotiation_margin_pct is not None
    ]

    avg_asking_ppm2 = _mean_int(asking_ppm2_values)
    avg_closing_ppm2 = _mean_int(closing_ppm2_values)
    gap_pct = None
    if avg_asking_ppm2 and avg_closing_ppm2:
        gap_pct = _round_pct((1 - (avg_closing_ppm2 / avg_asking_ppm2)) * 100)

    summary = MarketTransactionsSummary(
        total_transactions=len(transactions),
        avg_asking_price=_mean_int(asking_prices),
        avg_closing_price=_mean_int(closing_prices),
        avg_asking_price_per_m2=avg_asking_ppm2,
        avg_closing_price_per_m2=avg_closing_ppm2,
        asking_vs_closing_gap_pct=gap_pct,
        negotiation_margin_pct=_round_pct(mean(margin_values)) if margin_values else None,
        sample_size=len(transactions),
        chart_series=_build_chart_series(transactions),
    )

    return MarketTransactions(summary=summary, transactions=transactions)
