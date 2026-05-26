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
STAGE_LABELS_ES = {
    "same_street": "Misma calle",
    "same_microzone": "Misma microzona",
    "same_local_area": "Mismo distrito",
    "municipality": "Municipio",
}
STAGE_RADIUS_METERS = {
    "same_street": 150,
    "same_microzone": 500,
    "same_local_area": 1500,
    "municipality": 3000,
}


def _format_eur(value: Optional[int]) -> str:
    """1234567 → '1.234.567 €' (Spanish locale formatting, no dependency on locale module)."""
    if value is None:
        return ""
    return f"{int(value):,} €".replace(",", ".")


def _stage_label(stage: Optional[str]) -> str:
    if not stage:
        return "Zona comparable"
    return STAGE_LABELS_ES.get(stage, stage.replace("_", " "))


def _stage_radius_meters(stage: Optional[str]) -> int:
    return STAGE_RADIUS_METERS.get(stage or "", 3000)


def _listing_dicts(valuation: ValuationResponse) -> list[dict[str, Any]]:
    listings: list[dict[str, Any]] = []
    for listing in valuation.listings:
        data = listing.model_dump()
        data["source_stage_label"] = _stage_label(listing.source_stage)
        listings.append(data)
    return listings


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
    include_comparables: bool = True,
) -> str:
    """Render the full HTML report. Idempotent and dependency-light.

    Set ``include_comparables=False`` to drop the per-listing comparables
    section from the PDF. Aggregate stats (avg €/m², total count) stay in the
    report — only the individual Idealista cards are hidden, which is the
    variant coaches and clients sometimes prefer for a cleaner deliverable.
    """

    stats = valuation.stats
    regression = valuation.regression
    template = _ENV.get_template(TEMPLATE_NAME)

    selected_unit = request_payload.get("selected_cadastral_unit") or {}
    selected_address = request_payload.get("selected_address") or {}
    full_address = (
        selected_address.get("label")
        or request_payload.get("address")
        or valuation.municipio.road
        or ""
    )

    return template.render(
        # Header
        generated_at=(generated_at or datetime.now()).strftime("%d/%m/%Y · %H:%M"),
        lead=lead,
        # Property
        address=valuation.municipio.road or request_payload.get("address") or "",
        full_address=full_address,
        cadastral_reference=selected_unit.get("cadastral_reference"),
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
        final_stage_label=_stage_label(valuation.search_metadata.final_stage),
        search_radius_meters=_stage_radius_meters(valuation.search_metadata.final_stage),
        # Market KPIs
        avg_price=stats.avg_price,
        avg_price_per_m2=stats.avg_price_per_m2,
        # Comparables (rendered as raw dicts so the template doesn't have to
        # learn about Pydantic accessors)
        listings=_listing_dicts(valuation),
        include_comparables=include_comparables,
        # Methodology block
        r_squared_pct=(
            round(regression.r_squared * 100, 1)
            if regression and regression.r_squared is not None
            else "?"
        ),
        regression_sample_size=regression.sample_size if regression else 0,
    )
