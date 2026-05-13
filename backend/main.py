import logging
import os
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from typing import Optional

from geocoder import (
    get_municipio_from_address,
    municipio_from_resolved_address,
    reverse_geocode,
    suggest_addresses,
)
from market_pricing import get_median_sqm_price
from market_transactions import build_market_transactions_mock
from models import (
    ComparablesDataset,
    DatasetRow,
    Listing,
    ResolvedAddress,
    ValuationRequest,
    ValuationResponse,
    ValuationStats,
)
from scraper import scrape_idealista_listings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATASET_MAX_ROWS = 6
DATASET_MIN_ROWS = 3


def _flag(value: Optional[bool]) -> int:
    return 1 if value else 0


def build_dataset(
    listings: list[Listing],
    *,
    median_sqm_price: Optional[float] = None,
) -> ComparablesDataset:
    def _closing(m2: Optional[int]) -> Optional[int]:
        if median_sqm_price is None or m2 is None:
            return None
        return int(round(m2 * median_sqm_price))

    def _negotiation(price: Optional[int], closing: Optional[int]) -> Optional[float]:
        if price is None or not price or closing is None:
            return None
        return round(closing / price, 4)

    rows: list[DatasetRow] = []
    for listing in listings[:DATASET_MAX_ROWS]:
        closing = _closing(listing.m2)
        rows.append(
            DatasetRow(
                listing_url=listing.url,
                address=listing.address,
                metros=listing.m2,
                precio=listing.price,
                habitaciones=listing.bedrooms,
                banos=listing.bathrooms,
                planta=listing.floor_number,
                ascensor=_flag(listing.has_elevator),
                piscina=_flag(listing.has_pool),
                jardin=_flag(listing.has_garden),
                garaje=_flag(listing.has_garage),
                trastero=_flag(listing.has_storage_room),
                closing_value=closing,
                negotiation_factor=_negotiation(listing.price, closing),
            )
        )
    return ComparablesDataset(
        rows=rows,
        row_count=len(rows),
        min_required=DATASET_MIN_ROWS,
        max_allowed=DATASET_MAX_ROWS,
    )


def log_dataset(dataset: ComparablesDataset) -> None:
    logger.info("Comparables dataset (%d rows)", dataset.row_count)
    logger.info(
        "| # | metros | precio | closing | neg. | hab | banos | planta | asc | pis | jar | gar | tra |"
    )
    logger.info(
        "|---|--------|--------|---------|------|-----|-------|--------|-----|-----|-----|-----|-----|"
    )
    for idx, row in enumerate(dataset.rows, start=1):
        neg = (
            f"{row.negotiation_factor:.4f}"
            if row.negotiation_factor is not None
            else "-"
        )
        logger.info(
            "| %d | %s | %s | %s | %s | %s | %s | %s | %d | %d | %d | %d | %d |",
            idx,
            row.metros if row.metros is not None else "-",
            row.precio if row.precio is not None else "-",
            row.closing_value if row.closing_value is not None else "-",
            neg,
            row.habitaciones if row.habitaciones is not None else "-",
            row.banos if row.banos is not None else "-",
            row.planta if row.planta is not None else "-",
            row.ascensor,
            row.piscina,
            row.jardin,
            row.garaje,
            row.trastero,
        )
    if dataset.row_count < dataset.min_required:
        logger.warning(
            "Dataset has %d rows, below recommended minimum of %d",
            dataset.row_count,
            dataset.min_required,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("House Valuation API starting up")
    yield
    logger.info("House Valuation API shutting down")


app = FastAPI(
    title="House Valuation API",
    description="MVP — estimates your home value using real-time Idealista listings",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the frontend from ../frontend/
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", include_in_schema=False)
async def serve_frontend():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/addresses/autocomplete", response_model=list[ResolvedAddress])
async def autocomplete_addresses(
    q: str = Query(..., min_length=3),
    limit: int = Query(5, ge=1, le=8),
):
    try:
        return await suggest_addresses(q, limit=limit)
    except Exception as exc:
        logger.error(f"Address autocomplete failed: {exc}", exc_info=True)
        raise HTTPException(status_code=502, detail="Address autocomplete unavailable")


@app.get("/api/addresses/reverse", response_model=ResolvedAddress)
async def reverse_address(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
):
    try:
        return await reverse_geocode(lat, lon)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error(f"Reverse geocoding failed: {exc}", exc_info=True)
        raise HTTPException(status_code=502, detail="Reverse geocoding unavailable")


@app.post("/api/valuation", response_model=ValuationResponse)
async def get_valuation(request: ValuationRequest):
    """
    Main valuation endpoint.
    1. Geocode the address to extract the municipio.
    2. Scrape Idealista for comparable listings.
    3. Compute basic price statistics and an estimated value.
    """
    request_started_at = perf_counter()
    valuation_address = request.selected_address.label if request.selected_address else request.address

    # --- Step 1: Geocode ---
    try:
        municipio = (
            municipio_from_resolved_address(request.selected_address)
            if request.selected_address
            else await get_municipio_from_address(request.address)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error(f"Geocoding failed: {exc}", exc_info=True)
        raise HTTPException(status_code=502, detail="Geocoding service unavailable")

    logger.info(f"Municipio resolved: {municipio.name} (slug: {municipio.slug})")

    median_sqm_price = get_median_sqm_price(municipio.name)
    if median_sqm_price is None:
        logger.warning(
            "Median sqm price (second_hand 2026Q1) not found for %s; "
            "closing_value/negotiation_factor will be null",
            municipio.name,
        )
    else:
        logger.info(
            "Median sqm price (second_hand 2026Q1) for %s: %.2f EUR/m2",
            municipio.name,
            median_sqm_price,
        )

    # --- Step 2: Scrape Idealista ---
    try:
        listings, search_url, search_metadata = await scrape_idealista_listings(
            address=valuation_address,
            municipio=municipio,
            bedrooms=request.bedrooms,
            bathrooms=request.bathrooms,
            m2=request.m2,
            max_listings=DATASET_MAX_ROWS,
        )
    except Exception as exc:
        logger.error(f"Scraping failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"Could not fetch listings from Idealista: {str(exc)}",
        )

    # --- Step 3: Statistics ---
    prices = [lst.price for lst in listings if lst.price]
    ppms = [lst.price_per_m2 for lst in listings if lst.price_per_m2]

    avg_ppm2 = int(sum(ppms) / len(ppms)) if ppms else None
    estimated = int(avg_ppm2 * request.m2) if avg_ppm2 else None

    stats = ValuationStats(
        total_comparables=len(listings),
        avg_price=int(sum(prices) / len(prices)) if prices else None,
        min_price=min(prices) if prices else None,
        max_price=max(prices) if prices else None,
        avg_price_per_m2=avg_ppm2,
        estimated_value=estimated,
        price_range_low=int(estimated * 0.90) if estimated else None,
        price_range_high=int(estimated * 1.10) if estimated else None,
    )
    market_transactions = build_market_transactions_mock(
        valuation_address,
        municipio,
        m2=request.m2,
        bedrooms=request.bedrooms,
        bathrooms=request.bathrooms,
        listing_avg_price_per_m2=avg_ppm2,
    )

    dataset = build_dataset(listings, median_sqm_price=median_sqm_price)
    log_dataset(dataset)

    logger.info(
        "Valuation finished in %sms using stage %s",
        int((perf_counter() - request_started_at) * 1000),
        search_metadata.final_stage,
    )

    return ValuationResponse(
        municipio=municipio,
        listings=listings,
        stats=stats,
        search_url=search_url,
        search_metadata=search_metadata,
        market_transactions=market_transactions,
        dataset=dataset,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
