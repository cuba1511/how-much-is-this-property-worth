"""HTML rendering for the valuation report.

Takes a `ValuationResponse` (+ optional lead) and produces the HTML string that
gets piped into Playwright for PDF generation. Pure function — no I/O beyond
loading the Jinja2 template from disk once at import time.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from models import LeadInfo, ValuationResponse

TEMPLATE_DIR = Path(__file__).parent
TEMPLATE_NAME = "template.html"


def _format_eur(value: Optional[int]) -> str:
    """1234567 → '1.234.567 €' (Spanish locale formatting, no dependency on locale module)."""
    if value is None:
        return ""
    return f"{int(value):,} €".replace(",", ".")


def _build_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["money"] = _format_eur
    return env


_ENV = _build_env()


def render_report_html(
    *,
    valuation: ValuationResponse,
    request_payload: dict[str, Any],
    lead: Optional[LeadInfo] = None,
    generated_at: Optional[datetime] = None,
) -> str:
    """Render the full HTML report. Idempotent and dependency-light."""

    stats = valuation.stats
    regression = valuation.regression
    template = _ENV.get_template(TEMPLATE_NAME)

    return template.render(
        # Header
        generated_at=(generated_at or datetime.now()).strftime("%d/%m/%Y · %H:%M"),
        lead=lead,
        # Property
        address=valuation.municipio.road or request_payload.get("address") or "",
        municipio=valuation.municipio.name,
        request_m2=request_payload.get("m2"),
        request_bedrooms=request_payload.get("bedrooms"),
        request_bathrooms=request_payload.get("bathrooms"),
        property_type=request_payload.get("property_type"),
        property_condition=request_payload.get("property_condition"),
        # Hero
        estimated_value=stats.estimated_value,
        price_range_low=stats.price_range_low,
        price_range_high=stats.price_range_high,
        estimation_method=stats.estimation_method,
        confidence_method=stats.confidence_method,
        total_comparables=stats.total_comparables,
        # Market KPIs
        avg_price=stats.avg_price,
        avg_price_per_m2=stats.avg_price_per_m2,
        # Comparables (rendered as raw dicts so the template doesn't have to
        # learn about Pydantic accessors)
        listings=[listing.model_dump() for listing in valuation.listings],
        # Methodology block
        r_squared_pct=(
            round(regression.r_squared * 100, 1)
            if regression and regression.r_squared is not None
            else "?"
        ),
        regression_sample_size=regression.sample_size if regression else 0,
    )
