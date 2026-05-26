"""HTML rendering for the valuation report.

Takes a `ValuationResponse` (+ optional lead) and produces the HTML string that
gets piped into Playwright for PDF generation. Pure function — no I/O beyond
loading the Jinja2 template from disk once at import time.
"""

from __future__ import annotations

import base64
import logging
import math
import os
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape

from models import LeadInfo, TransactionDetail, ValuationResponse

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent
TEMPLATE_NAME = "template.html"
DEFAULT_BOOKING_URL = "https://prophero.com"
SPANISH_MONTHS_SHORT = {
    1: "ene",
    2: "feb",
    3: "mar",
    4: "abr",
    5: "may",
    6: "jun",
    7: "jul",
    8: "ago",
    9: "sept",
    10: "oct",
    11: "nov",
    12: "dic",
}
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


def _format_eur_or_dash(value: Optional[int]) -> str:
    return _format_eur(value) if value is not None else "—"


def _format_int(value: Optional[int]) -> str:
    if value is None:
        return "—"
    return f"{int(value):,}".replace(",", ".")


def _format_price_per_m2(value: Optional[int]) -> str:
    if value is None:
        return "—"
    return f"{_format_int(value)} €/m²"


def _format_percent(value: Optional[float]) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


def _format_currency_range(low: Optional[int], high: Optional[int]) -> str:
    if low is None or high is None:
        return "—"
    if low == high:
        return _format_eur(low)
    return f"{_format_int(low)} – {_format_eur(high)}"


def _round_to_step(value: float, step: int) -> int:
    return int(round(value / step) * step)


def _price_band(anchor: Optional[int], spread_pct: float, step: int = 1000) -> dict[str, Optional[int]]:
    if anchor is None:
        return {"low": None, "high": None}
    raw_low = anchor * (1 - spread_pct)
    raw_high = anchor * (1 + spread_pct)
    low = max(0, _round_to_step(raw_low, step))
    high = max(low + step, _round_to_step(raw_high, step))
    return {"low": low, "high": high}


def _price_per_m2(total: Optional[int], m2: Optional[int]) -> Optional[int]:
    if not total or not m2:
        return None
    return round(total / m2)


def _capital_gain(exit_price: Optional[int], invested: Optional[int]) -> Optional[int]:
    if exit_price is None or invested is None:
        return None
    return exit_price - invested


def _roi_percent(gain: Optional[int], invested: Optional[int]) -> Optional[float]:
    if gain is None or not invested:
        return None
    return (gain / invested) * 100


def _format_period(period: Optional[str]) -> str:
    if not period:
        return "—"
    parts = period.split("-")
    if len(parts) < 2:
        return period
    try:
        year = int(parts[0])
        month = int(parts[1])
    except ValueError:
        return period
    return f"{SPANISH_MONTHS_SHORT.get(month, parts[1])} {year}"


def _format_date_es(value: Optional[str]) -> str:
    if not value:
        return "—"
    candidates = [value[:10], value]
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            return f"{parsed.day} {SPANISH_MONTHS_SHORT.get(parsed.month, parsed.strftime('%b'))} {parsed.year}"
        except ValueError:
            continue
    return value


def _stage_label(stage: Optional[str]) -> str:
    if not stage:
        return "Zona comparable"
    return STAGE_LABELS_ES.get(stage, stage.replace("_", " "))


def _stage_radius_meters(stage: Optional[str]) -> int:
    return STAGE_RADIUS_METERS.get(stage or "", 3000)


def _total_spent(transaction: Optional[TransactionDetail]) -> Optional[int]:
    if transaction is None:
        return None
    return transaction.final_total_price


MAP_TILE_SIZE = 256
MAP_DEFAULT_ZOOM = 15
MAP_HTTP_TIMEOUT_S = 4.0
MAP_USER_AGENT = "PropHero-Report/1.0 (https://prophero.com; reports@prophero.com)"
MAP_VIEWPORT_WIDTH = 320
MAP_VIEWPORT_HEIGHT = 180


def _deg_to_global_pixels(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """Web Mercator lat/lon → global pixel coords at the given zoom level."""
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    x = (lon + 180.0) / 360.0 * n * MAP_TILE_SIZE
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n * MAP_TILE_SIZE
    return x, y


def _fetch_image_bytes(client: httpx.Client, url: str) -> Optional[bytes]:
    try:
        response = client.get(url)
    except httpx.HTTPError as exc:
        logger.warning("Map asset fetch failed (%s): %s", url, exc)
        return None
    if response.status_code != 200:
        logger.warning("Map asset non-200 (%s): %s", url, response.status_code)
        return None
    content_type = response.headers.get("content-type", "")
    if not content_type.startswith("image/"):
        logger.warning("Map asset wrong content-type (%s): %s", url, content_type)
        return None
    return response.content


def _mapbox_static_image(client: httpx.Client, lat: float, lon: float) -> Optional[bytes]:
    token = os.environ.get("MAPBOX_TOKEN")
    if not token:
        return None
    url = (
        "https://api.mapbox.com/styles/v1/mapbox/streets-v12/static/"
        f"pin-l+2050f6({lon},{lat})/{lon},{lat},{MAP_DEFAULT_ZOOM},0/"
        f"{MAP_VIEWPORT_WIDTH * 2}x{MAP_VIEWPORT_HEIGHT * 2}@2x"
        f"?access_token={quote(token)}"
    )
    return _fetch_image_bytes(client, url)


def _osm_tile_html(
    client: httpx.Client,
    lat: float,
    lon: float,
    zoom: int = MAP_DEFAULT_ZOOM,
) -> Optional[str]:
    """Build a self-contained HTML block: 2×2 OSM tiles with a pin overlay.

    Tiles are downloaded once and inlined as base64 so Chromium never has to
    reach out to the network when rendering the PDF — that's been the failure
    mode in every prod attempt so far.
    """
    px, py = _deg_to_global_pixels(lat, lon, zoom)
    cx_tile = int(px // MAP_TILE_SIZE)
    cy_tile = int(py // MAP_TILE_SIZE)
    fx = px - cx_tile * MAP_TILE_SIZE  # 0..256, pin within its tile
    fy = py - cy_tile * MAP_TILE_SIZE

    if fx < MAP_TILE_SIZE / 2:
        tx_start = cx_tile - 1
        pin_x_in_grid = MAP_TILE_SIZE + fx
    else:
        tx_start = cx_tile
        pin_x_in_grid = fx
    if fy < MAP_TILE_SIZE / 2:
        ty_start = cy_tile - 1
        pin_y_in_grid = MAP_TILE_SIZE + fy
    else:
        ty_start = cy_tile
        pin_y_in_grid = fy

    tile_imgs: list[str] = []
    for dy in range(2):
        for dx in range(2):
            tx = tx_start + dx
            ty = ty_start + dy
            url = f"https://tile.openstreetmap.org/{zoom}/{tx}/{ty}.png"
            payload = _fetch_image_bytes(client, url)
            if not payload:
                return None
            b64 = base64.b64encode(payload).decode("ascii")
            tile_imgs.append(
                f'<img src="data:image/png;base64,{b64}" '
                f'style="position:absolute;left:{dx * MAP_TILE_SIZE}px;'
                f'top:{dy * MAP_TILE_SIZE}px;width:{MAP_TILE_SIZE}px;'
                f'height:{MAP_TILE_SIZE}px;display:block;">'
            )

    grid_side = MAP_TILE_SIZE * 2
    offset_x = MAP_VIEWPORT_WIDTH / 2 - pin_x_in_grid
    offset_y = MAP_VIEWPORT_HEIGHT / 2 - pin_y_in_grid

    pin_svg = (
        '<svg width="28" height="40" viewBox="0 0 28 40" '
        'xmlns="http://www.w3.org/2000/svg" '
        f'style="position:absolute;left:{MAP_VIEWPORT_WIDTH / 2 - 14:.1f}px;'
        f'top:{MAP_VIEWPORT_HEIGHT / 2 - 38:.1f}px;pointer-events:none;">'
        '<path d="M14 0C6.3 0 0 6.1 0 13.7 0 24 14 40 14 40s14-16 14-26.3'
        'C28 6.1 21.7 0 14 0z" fill="#2050f6"/>'
        '<circle cx="14" cy="14" r="5.5" fill="#ffffff"/>'
        "</svg>"
    )

    return (
        f'<div style="position:relative;width:{MAP_VIEWPORT_WIDTH}px;'
        f'height:{MAP_VIEWPORT_HEIGHT}px;overflow:hidden;border-radius:10px;'
        'background:#dee5ea;">'
        f'<div style="position:absolute;left:{offset_x:.1f}px;'
        f'top:{offset_y:.1f}px;width:{grid_side}px;height:{grid_side}px;">'
        f'{"".join(tile_imgs)}</div>{pin_svg}</div>'
    )


def _placeholder_map_html(label: Optional[str], lat: float, lon: float) -> str:
    """Static SVG used only when every real-map fetch fails."""
    safe_label = escape(label or "Propiedad")
    svg = f"""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 320 180' width='320' height='180'>
  <rect width='320' height='180' fill='#e7eef5'/>
  <g stroke='#c4d2e0' stroke-width='6' fill='none'>
    <path d='M-10 60 C 80 30, 160 100, 260 80 S 330 50, 340 40'/>
    <path d='M-10 130 C 90 110, 170 140, 260 130 S 330 110, 340 100'/>
  </g>
  <path d='M160 60c-12 0-22 9-22 21 0 16 22 39 22 39s22-23 22-39c0-12-10-21-22-21z' fill='#2050f6'/>
  <circle cx='160' cy='80' r='8' fill='#ffffff'/>
  <text x='160' y='162' text-anchor='middle' font-family='Inter,Arial,sans-serif' font-size='12' font-weight='700' fill='#1e252d'>{safe_label}</text>
  <text x='160' y='176' text-anchor='middle' font-family='Inter,Arial,sans-serif' font-size='9' fill='#596b7d'>{lat:.4f}, {lon:.4f}</text>
</svg>"""
    return (
        f'<div style="width:{MAP_VIEWPORT_WIDTH}px;height:{MAP_VIEWPORT_HEIGHT}px;'
        'overflow:hidden;border-radius:10px;">'
        f"{svg}</div>"
    )


def _build_map_html(
    lat: Optional[float], lon: Optional[float], label: Optional[str]
) -> Optional[str]:
    """Return a self-contained HTML map block, or ``None`` if no coords."""
    if lat is None or lon is None:
        return None
    try:
        with httpx.Client(
            timeout=MAP_HTTP_TIMEOUT_S,
            headers={"User-Agent": MAP_USER_AGENT, "Referer": "https://prophero.com"},
            follow_redirects=True,
        ) as client:
            mapbox_png = _mapbox_static_image(client, lat, lon)
            if mapbox_png:
                b64 = base64.b64encode(mapbox_png).decode("ascii")
                return (
                    f'<img src="data:image/png;base64,{b64}" alt="Mapa de {escape(label or "")}"'
                    f' style="display:block;width:{MAP_VIEWPORT_WIDTH}px;'
                    f'height:{MAP_VIEWPORT_HEIGHT}px;object-fit:cover;'
                    'border-radius:10px;">'
                )

            tile_html = _osm_tile_html(client, lat, lon)
            if tile_html:
                return tile_html
    except Exception as exc:  # noqa: BLE001
        logger.warning("Map composition failed: %s", exc, exc_info=True)

    return _placeholder_map_html(label, lat, lon)


def _listing_dicts(valuation: ValuationResponse) -> list[dict[str, Any]]:
    listings: list[dict[str, Any]] = []
    for listing in valuation.listings:
        data = listing.model_dump()
        data["source_stage_label"] = _stage_label(listing.source_stage)
        listings.append(data)
    return listings


def _build_scenario(
    *,
    label: str,
    description: str,
    band: dict[str, Optional[int]],
    timing: str,
    timing_hint: str,
    invested: Optional[int],
) -> dict[str, Any]:
    gain_low = _capital_gain(band["low"], invested)
    gain_high = _capital_gain(band["high"], invested)
    roi_low = _roi_percent(gain_low, invested)
    roi_high = _roi_percent(gain_high, invested)
    return {
        "label": label,
        "description": description,
        "range": _format_currency_range(band["low"], band["high"]),
        "gain": _format_currency_range(gain_low, gain_high),
        "roi": (
            "—"
            if roi_low is None or roi_high is None
            else _format_percent(roi_low)
            if roi_low == roi_high
            else f"{_format_percent(roi_low)} – {_format_percent(roi_high)}"
        ),
        "timing": timing,
        "timing_hint": timing_hint,
    }


def _market_reading(
    *,
    appreciation_town: Optional[str],
    appreciation_pct: Optional[float],
    has_comparables: bool,
    recommended_range: str,
) -> str:
    if appreciation_town and appreciation_pct is not None and has_comparables:
        return (
            f"La zona de {appreciation_town} ha apreciado un {_format_percent(appreciation_pct)} "
            f"desde la firma. El rango recomendado ({recommended_range}) se construye sobre "
            "comparables activos hoy y captura plusvalía sin alejarse del mercado."
        )
    if appreciation_town and appreciation_pct is not None:
        return (
            f"La zona de {appreciation_town} ha apreciado un {_format_percent(appreciation_pct)} "
            f"desde la firma. Sin comparables individuales, anclamos el rango recomendado "
            f"({recommended_range}) en la mediana €/m² del municipio publicada por TF Labs."
        )
    if has_comparables:
        return (
            "El rango recomendado se construye sobre los comparables activos en el municipio. "
            "Los tres escenarios cubren liquidez vs maximización de retorno."
        )
    return (
        "Sin comparables individuales, anclamos el rango recomendado en la mediana €/m² "
        "del municipio (serie TF Labs). Útil como termómetro de zona; menos preciso que "
        "con comparables activos."
    )


def _methodology_source(stats_method: Optional[str], no_scrape: bool) -> str:
    if no_scrape:
        return "mediana €/m² del municipio (serie pública TF Labs) aplicada a la superficie del inmueble"
    if stats_method == "ols_lstsq":
        return "regresión sobre comparables activos en Idealista (precio, m², habitaciones, baños)"
    return "mediana €/m² de comparables activos en Idealista aplicada a la superficie del inmueble"


def _build_report_context(
    *,
    valuation: ValuationResponse,
    request_payload: dict[str, Any],
    transaction: Optional[TransactionDetail],
) -> dict[str, Any]:
    stats = valuation.stats
    appreciation = valuation.market_appreciation
    request_m2 = request_payload.get("m2")
    invested = _total_spent(transaction)
    recommended_anchor = stats.estimated_value
    quick_anchor = stats.price_range_low or (round(recommended_anchor * 0.94) if recommended_anchor else None)
    aspirational_anchor = stats.price_range_high or (
        round(recommended_anchor * 1.04) if recommended_anchor else None
    )
    quick_band = _price_band(quick_anchor, 0.025)
    recommended_band = _price_band(recommended_anchor, 0.03)
    aspirational_band = _price_band(aspirational_anchor, 0.025)

    purchase_ppm2 = _price_per_m2(invested, request_m2)
    current_ppm2 = (
        round(appreciation.to_eur_per_m2)
        if appreciation
        else _price_per_m2(recommended_anchor, request_m2) or stats.avg_price_per_m2
    )
    ppm2_delta_pct = (
        appreciation.pct_change * 100
        if appreciation
        else ((current_ppm2 - purchase_ppm2) / purchase_ppm2) * 100
        if current_ppm2 and purchase_ppm2
        else None
    )
    zone_plusvalia = (
        round(invested * appreciation.pct_change)
        if invested is not None and appreciation is not None
        else None
    )
    selected_address = request_payload.get("selected_address") or {}
    lat = selected_address.get("lat") or valuation.municipio.lat
    lon = selected_address.get("lon") or valuation.municipio.lon
    map_label = appreciation.town_name if appreciation else valuation.municipio.name
    map_html = _build_map_html(lat, lon, map_label)
    has_comparables = len(valuation.listings) > 0
    no_scrape = valuation.search_metadata.strategy == "no_scrape"
    recommended_range = _format_currency_range(recommended_band["low"], recommended_band["high"])
    appreciation_pct = appreciation.pct_change * 100 if appreciation else None

    return {
        "is_coach": transaction is not None,
        "kicker": "Reporte inversor" if transaction else "Reporte de valoración",
        "headline": (
            "Cuánto ha ganado y cómo salir al mercado"
            if transaction
            else "Cuánto vale tu propiedad hoy"
        ),
        "subtitle": (
            "Este resumen traduce la valoración en plusvalía, rango de salida y escenarios "
            "comerciales para que el cliente entienda el retorno de su inversión."
            if transaction
            else "Esta es una lectura cuantitativa del mercado para tu inmueble: rango de venta, "
            "evolución de zona y escenarios posibles para salir al mercado."
        ),
        "overall_range": _format_currency_range(quick_band["low"], aspirational_band["high"]),
        "recommended_range": recommended_range,
        "settlement_date": _format_date_es(transaction.real_settlement_date if transaction else None),
        "invested": _format_eur_or_dash(invested),
        "purchase_ppm2": _format_price_per_m2(purchase_ppm2),
        "current_ppm2_label": (
            f"€/m² zona ({_format_period(appreciation.to_period)})"
            if appreciation
            else "€/m² zona hoy"
        ),
        "current_ppm2": _format_price_per_m2(current_ppm2),
        "ppm2_delta": _format_percent(ppm2_delta_pct) if ppm2_delta_pct is not None else None,
        "zone_plusvalia": _format_eur_or_dash(zone_plusvalia),
        "zone_plusvalia_pct": _format_percent(appreciation_pct) if appreciation_pct is not None else None,
        "zone_metric_label": (
            "Plusvalía de zona"
            if appreciation and transaction
            else "Apreciación de zona"
            if appreciation
            else "Ganancia (rango recomendado)"
            if transaction
            else "Rango recomendado"
        ),
        "recommended_gain": _format_currency_range(
            _capital_gain(recommended_band["low"], invested),
            _capital_gain(recommended_band["high"], invested),
        ),
        "appreciation": {
            "town_name": appreciation.town_name,
            "pct": _format_percent(appreciation_pct),
            "from_period": _format_period(appreciation.from_period),
            "to_period": _format_period(appreciation.to_period),
            "from_ppm2": _format_price_per_m2(round(appreciation.from_eur_per_m2)),
            "to_ppm2": _format_price_per_m2(round(appreciation.to_eur_per_m2)),
            "months_elapsed": appreciation.months_elapsed,
            "annualized": (
                _format_percent(appreciation.annualized_pct_change * 100)
                if appreciation.annualized_pct_change is not None
                else "—"
            ),
        }
        if appreciation
        else None,
        "map_html": map_html,
        "scenarios": [
            _build_scenario(
                label="Venta rápida",
                description="Precio agresivo para acelerar interés y reducir tiempo en mercado.",
                band=quick_band,
                invested=invested,
                timing="Rotación rápida",
                timing_hint="Estrategia para minimizar días en mercado.",
            ),
            _build_scenario(
                label="Recomendado",
                description="Balance entre capturar plusvalía y mantener una salida realista.",
                band=recommended_band,
                invested=invested,
                timing="Timing equilibrado",
                timing_hint="Punto de partida sugerido al cliente.",
            ),
            _build_scenario(
                label="Aspiracional",
                description="Para maximizar precio si el cliente puede esperar más.",
                band=aspirational_band,
                invested=invested,
                timing="Más tiempo en mercado",
                timing_hint="Requiere paciencia y revisión de precio si no hay tracción.",
            ),
        ],
        "market_reading": _market_reading(
            appreciation_town=appreciation.town_name if appreciation else None,
            appreciation_pct=appreciation_pct,
            has_comparables=has_comparables,
            recommended_range=recommended_range,
        ),
        "methodology_source": _methodology_source(stats.estimation_method, no_scrape),
        "has_comparables": has_comparables,
    }


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
    transaction: Optional[TransactionDetail] = None,
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

    booking_url = os.environ.get("PROPHERO_BOOKING_URL", DEFAULT_BOOKING_URL)
    report = _build_report_context(
        valuation=valuation,
        request_payload=request_payload,
        transaction=transaction,
    )

    return template.render(
        # Header
        generated_at=(generated_at or datetime.now()).strftime("%d/%m/%Y · %H:%M"),
        lead=lead,
        booking_url=booking_url,
        report=report,
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
