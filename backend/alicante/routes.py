"""FastAPI routes for the Alicante MVP.

Exposes two endpoints, both completely isolated from production:

- `POST /api/valuation/alicante` — drop-in for `/api/valuation` that uses
  the local SQLite snapshot instead of Bright Data + Idealista, and the
  real-data transactions layer instead of the seeded mock. **Solo acepta
  direcciones en Alicante/Alacant** — el resto se rechaza con 422.
- `GET  /api/valuation/alicante/status` — quick health check for the
  dataset (loaded? how many rows?).

Production `/api/valuation` is NOT touched and will keep using the
scraper. Removing the entire `alicante/` package removes the MVP cleanly.
"""
from __future__ import annotations

import logging
import re
from time import perf_counter
from typing import Optional

from fastapi import APIRouter, HTTPException

from geocoding import get_municipio_from_address, municipio_from_resolved_address
from models import MunicipioInfo, ValuationRequest, ValuationResponse, ValuationStats
from valuation.regression import fit_listing_regression

from alicante import storage
from alicante._pipeline import (
    DATASET_MAX_ROWS,
    build_dataset,
    choose_estimate,
    confidence_interval,
    log_dataset,
)
from alicante.coverage import COVERAGE_SLUGS, municipio_in_coverage
from alicante.listings_provider import query_alicante_listings
from alicante.transactions import build_alicante_transactions

logger = logging.getLogger(__name__)

router = APIRouter(tags=["alicante-mvp"])


# Heurística mínima para "la dirección incluye número de portal".
# Buscamos al menos un dígito en la primera coma-segmento del label, que es
# donde típicamente vive el número (`"Calle Mayor 12, Alicante, España"`).
# Es una validación blanda — la verificación real la hace el geocoder al
# resolver lat/lon. Sin esto, "Alicante" o "Alicante centro" cuelan y la
# valoración acaba siendo la del centroide del municipio.
_HOUSE_NUMBER_RE = re.compile(r"\d")


def _looks_like_street_with_number(label: str) -> bool:
    """True if the first comma-segment of the label contains a digit."""
    if not label:
        return False
    head = label.split(",", 1)[0].strip()
    return bool(_HOUSE_NUMBER_RE.search(head))


@router.post(
    "/api/valuation/alicante",
    response_model=ValuationResponse,
    summary="MVP Alicante — solo direcciones en Alicante/Alacant (calle + número)",
)
async def get_valuation_alicante(request: ValuationRequest):
    """Valoración MVP usando el dataset local de Alicante.

    **Cobertura:** únicamente direcciones cuyo municipio resuelva a
    Alicante/Alacant (`admin3`). Si la dirección está en otra provincia,
    en otro municipio de Alicante (Elche, Benidorm, …) o no se puede
    resolver, el endpoint devuelve **422** en vez de hacer una valoración
    poco fiable. Para esos casos usa `POST /api/valuation` (scraper).

    **Formato esperado:** calle + número de portal, idealmente con el
    municipio. Ejemplos válidos:

    - `"Calle Gravina 5, Alicante"`
    - `"Avenida Maisonnave 23, Alicante"`
    - `"Calle Mayor 12, 03001 Alicante"`

    Ejemplos rechazados (sin número de portal o fuera de cobertura):

    - `"Alicante"` → 422 (falta número de portal)
    - `"Calle Mayor, Madrid"` → 422 (no es Alicante)
    - `"03003"` → 422 (solo CP, no resuelve a calle)

    Si el frontend ha resuelto la dirección con autocompletado y manda
    `selected_address`, se usa ese label como fuente de verdad.

    **Diferencias frente a `/api/valuation`:**

    - Listings desde SQLite local (<50 ms vs 15-60 s del scraper).
    - `market_transactions` con KPIs reales del dataset (`alicante_transactions`,
      boundary 224, op_type=10) en lugar del mock semilla.

    **Errores:**

    - `422` — dataset no cargado / dirección sin número / fuera de cobertura.
    - `502` — fallo al consultar el dataset local.
    """
    request_started_at = perf_counter()

    if storage.listings_count() == 0:
        raise HTTPException(
            status_code=422,
            detail=(
                "Dataset Alicante no cargado. Ejecuta `make load-alicante` "
                "(esperando backend/data/alicante-mvp.xlsx)."
            ),
        )

    valuation_address = (
        request.selected_address.label if request.selected_address else request.address
    )

    if not _looks_like_street_with_number(valuation_address):
        raise HTTPException(
            status_code=422,
            detail=(
                "La dirección debe incluir calle y número de portal "
                "(ej. 'Calle Gravina 5, Alicante'). Recibido: "
                f"'{valuation_address}'."
            ),
        )

    # --- Step 1: Geocode (NO fallback — si no resuelve, 422) ---
    municipio: Optional[MunicipioInfo] = None
    geocoding_error: Optional[str] = None
    try:
        municipio = (
            municipio_from_resolved_address(request.selected_address)
            if request.selected_address
            else await get_municipio_from_address(request.address)
        )
    except Exception as exc:  # noqa: BLE001
        geocoding_error = str(exc)
        logger.warning("Alicante MVP: geocoding failed (%s)", exc)

    if municipio is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "No se pudo localizar la dirección. Asegúrate de incluir "
                "calle, número y municipio (ej. 'Calle Gravina 5, Alicante')."
                + (f" Detalle: {geocoding_error}" if geocoding_error else "")
            ),
        )

    # --- Step 2: Reject anything outside the Alicante coverage set ---
    if not municipio_in_coverage(municipio):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Este endpoint solo cubre direcciones en Alicante/Alacant. "
                f"La dirección resolvió a '{municipio.name}' "
                f"(slug='{municipio.slug}'). Slugs aceptados: "
                f"{sorted(COVERAGE_SLUGS)}. Usa POST /api/valuation para "
                f"el resto de España."
            ),
        )

    logger.info(
        "Alicante MVP: municipio=%s (%.4f,%.4f) — accepted by coverage",
        municipio.slug,
        municipio.lat or 0.0,
        municipio.lon or 0.0,
    )

    # --- Step 3: Local dataset (always — the only provider this endpoint uses) ---
    try:
        listings, search_url, search_metadata = await query_alicante_listings(
            valuation_address,
            municipio=municipio,
            bedrooms=request.bedrooms,
            bathrooms=request.bathrooms,
            m2=request.m2,
            max_listings=DATASET_MAX_ROWS,
        )
    except Exception as exc:
        logger.error("Alicante MVP: local dataset failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"Local dataset query failed: {str(exc)}",
        )

    # --- Step 4: Statistics (mirror of /api/valuation) ---
    prices = [lst.price for lst in listings if lst.price]
    ppms = [lst.price_per_m2 for lst in listings if lst.price_per_m2]
    avg_ppm2 = int(sum(ppms) / len(ppms)) if ppms else None
    baseline_estimate = int(avg_ppm2 * request.m2) if avg_ppm2 else None

    dataset = build_dataset(listings)
    log_dataset(dataset)

    regression = fit_listing_regression(dataset.rows)

    estimated, estimation_method = choose_estimate(
        regression=regression,
        baseline_estimate=baseline_estimate,
        m2=request.m2,
        bedrooms=request.bedrooms,
        bathrooms=request.bathrooms,
    )

    price_range_low, price_range_high, confidence_method = confidence_interval(
        estimated=estimated,
        avg_ppm2=avg_ppm2,
        ppms=ppms,
        request_m2=request.m2,
    )

    stats = ValuationStats(
        total_comparables=len(listings),
        avg_price=int(sum(prices) / len(prices)) if prices else None,
        min_price=min(prices) if prices else None,
        max_price=max(prices) if prices else None,
        avg_price_per_m2=avg_ppm2,
        estimated_value=estimated,
        price_range_low=price_range_low,
        price_range_high=price_range_high,
        estimation_method=estimation_method,
        confidence_method=confidence_method,
    )

    # --- Step 5: Real market transactions ---
    market_transactions = build_alicante_transactions(
        valuation_address,
        municipio,
        m2=request.m2,
        bedrooms=request.bedrooms,
        bathrooms=request.bathrooms,
        listing_avg_price_per_m2=avg_ppm2,
    )

    logger.info(
        "Alicante MVP finished in %sms — listings=%d, estimated=%s€, margin=%s%%",
        int((perf_counter() - request_started_at) * 1000),
        len(listings),
        f"{estimated:,}" if estimated else "n/a",
        market_transactions.summary.negotiation_margin_pct,
    )

    return ValuationResponse(
        municipio=municipio,
        listings=listings,
        stats=stats,
        search_url=search_url,
        search_metadata=search_metadata,
        market_transactions=market_transactions,
        dataset=dataset,
        regression=regression,
    )


@router.get(
    "/api/valuation/alicante/status",
    summary="MVP Alicante — estado del dataset local y municipios cubiertos",
)
async def get_alicante_status():
    """Quick health check for the Alicante MVP path.

    Returns whether the dataset is loaded, how many rows are in each table,
    the municipality slugs accepted by `POST /api/valuation/alicante`, and
    the expected address format. Useful for the frontend to show/hide the
    Alicante-test button (and the help text) based on real data availability.
    """
    listings_n = storage.listings_count()
    transactions_n = storage.transactions_count()
    return {
        "loaded": listings_n > 0,
        "listings": listings_n,
        "transactions": transactions_n,
        "coverage": sorted(COVERAGE_SLUGS),
        "endpoint": "/api/valuation/alicante",
        "address_format": "calle + número de portal, ej. 'Calle Gravina 5, Alicante'",
    }


__all__ = ["router"]
