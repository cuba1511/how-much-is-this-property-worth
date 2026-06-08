from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from models import MarketAppreciation  # noqa: E402
from report.renderer import _build_price_evolution_rows  # noqa: E402


def test_price_evolution_rows_start_with_real_purchase_ppm2():
    appreciation = MarketAppreciation(
        town_name="Massamagrell",
        settlement_date="2021-05-15",
        from_period="2021-05",
        from_eur_per_m2=1_169,
        to_period="2025-12",
        to_eur_per_m2=1_200,
        pct_change=0.0265,
        months_elapsed=55,
        sample_quality="exact",
        resolution_strategy="name_match",
    )

    rows = _build_price_evolution_rows(appreciation, purchase_ppm2=1_276)

    assert rows[0] == {"label": "2021", "value": "1.276 €/m²"}
    assert rows[-1] == {"label": "Hoy (Diciembre 2025)", "value": "1.200 €/m²"}
