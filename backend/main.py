import asyncio
import hashlib
import json
import logging
import os
import time
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
from market_transactions import build_market_transactions_mock
from models import (
    ComparablesDataset,
    DatasetRow,
    Listing,
    ResolvedAddress,
    ResolvedAddress,
    SimpleValuationResponse,
    ValuationRequest,
    ValuationResponse,
    ValuationStats,
)
from regression import fit_listing_regression
from scraper import scrape_idealista_listings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATASET_MAX_ROWS = 10
DATASET_MIN_ROWS = 3

# In-process TTL cache for /api/valuation/simple. The full valuation pipeline
# can take 40-70s when Idealista throws CAPTCHAs through Bright Data, which
# blows past Google Apps Script's 30s hard cap for custom functions. Caching
# repeated `(address, beds, baths, m2, fast)` requests gets us under 1s on
# warm hits, so demos via Google Sheets actually work once an address has
# been pre-warmed (with curl or the web app).
SIMPLE_VALUATION_CACHE_TTL_SECONDS = 60 * 60
_simple_valuation_cache: dict[str, tuple[float, SimpleValuationResponse]] = {}
_simple_valuation_cache_lock = asyncio.Lock()


def _simple_valuation_cache_key(request: ValuationRequest, fast: bool) -> str:
    payload = {
        "address": request.address,
        "bedrooms": request.bedrooms,
        "bathrooms": request.bathrooms,
        "m2": request.m2,
        "fast": fast,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()


def build_dataset(listings: list[Listing]) -> ComparablesDataset:
    rows: list[DatasetRow] = []
    for listing in listings[:DATASET_MAX_ROWS]:
        rows.append(
            DatasetRow(
                listing_url=listing.url,
                metros=listing.m2,
                precio=listing.price,
                habitaciones=listing.bedrooms,
                banos=listing.bathrooms,
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
    logger.info("| # | metros | precio | hab | banos |")
    logger.info("|---|--------|--------|-----|-------|")
    for idx, row in enumerate(dataset.rows, start=1):
        logger.info(
            "| %d | %s | %s | %s | %s |",
            idx,
            row.metros if row.metros is not None else "-",
            row.precio if row.precio is not None else "-",
            row.habitaciones if row.habitaciones is not None else "-",
            row.banos if row.banos is not None else "-",
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
    logger.info(
        "Request details — type: %s, condition: %s, features: %s",
        request.property_type,
        request.property_condition,
        request.features.model_dump() if request.features else None,
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

    dataset = build_dataset(listings)
    log_dataset(dataset)

    regression = fit_listing_regression(dataset.rows)
    if regression:
        alpha_repr = f"{regression.alpha:.3g}" if regression.alpha is not None else "n/a"
        r2_repr = (
            f"{regression.r_squared:.4f}" if regression.r_squared is not None else "n/a"
        )
        logger.info(
            "Regression (%s, n=%d, p=%d, alpha=%s, underdet=%s, R2=%s)",
            regression.method,
            regression.sample_size,
            regression.feature_count,
            alpha_repr,
            regression.is_underdetermined,
            r2_repr,
        )
        for coef in regression.coefficients:
            logger.info(
                "  %-26s (%s): %+.4f",
                coef.label,
                coef.kind,
                coef.coefficient,
            )
    else:
        logger.warning("Regression not produced (insufficient data)")

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
        regression=regression,
    )


@app.post(
    "/api/valuation/simple",
    response_model=SimpleValuationResponse,
    summary="Slim valuation contract for external integrations (Apps Script, Sheets, Zapier)",
)
async def get_valuation_simple(
    request: ValuationRequest,
    fast: bool = Query(
        False,
        description=(
            "If true, skip the Idealista scrape and return mocked market data "
            "instantly. Use this for Google Sheets / Apps Script demos where "
            "the 30s custom-function cap blocks real scraping."
        ),
    ),
) -> SimpleValuationResponse:
    """
    Stable, slim wrapper over /api/valuation. Returns only the four fields most
    integrations care about: price, asking_price, closing_price, negotiation_factor.

    NOTE: asking_price / closing_price / negotiation_factor currently come from the
    mocked market-transactions layer and are flagged with `is_mock: true`. The
    contract will not change when real data replaces the mock.

    Cached for 1h per `(address, beds, baths, m2, fast)` tuple.
    """
    cache_key = _simple_valuation_cache_key(request, fast)
    now = time.time()
    async with _simple_valuation_cache_lock:
        cached = _simple_valuation_cache.get(cache_key)
        if cached and (now - cached[0]) < SIMPLE_VALUATION_CACHE_TTL_SECONDS:
            logger.info(
                "Cache HIT /api/valuation/simple (fast=%s) — %s",
                fast,
                request.address,
            )
            return cached[1]

    if fast:
        response = await _build_fast_simple_valuation(request)
    else:
        response = await _build_lean_simple_valuation(request)

    async with _simple_valuation_cache_lock:
        _simple_valuation_cache[cache_key] = (time.time(), response)

    return response


async def _build_lean_simple_valuation(request: ValuationRequest) -> SimpleValuationResponse:
    """Real scrape, but WITHOUT per-listing detail enrichment.

    This is the path that used to fit in Apps Script's 30s custom-function cap
    before commit 9cebc75 added per-listing detail enrichment. The simple
    endpoint only needs aggregated price stats, so detail enrichment is wasted
    work here.

    Typical latency: 5-20s depending on Idealista CAPTCHA load.
    """
    valuation_address = (
        request.selected_address.label if request.selected_address else request.address
    )

    try:
        municipio = (
            municipio_from_resolved_address(request.selected_address)
            if request.selected_address
            else await get_municipio_from_address(request.address)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error(f"Geocoding failed (lean mode): {exc}", exc_info=True)
        raise HTTPException(status_code=502, detail="Geocoding service unavailable")

    try:
        listings, _search_url, _search_metadata = await scrape_idealista_listings(
            address=valuation_address,
            municipio=municipio,
            bedrooms=request.bedrooms,
            bathrooms=request.bathrooms,
            m2=request.m2,
            max_listings=DATASET_MAX_ROWS,
            enrich_details=False,
        )
    except Exception as exc:
        logger.error(f"Scraping failed (lean mode): {exc}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"Could not fetch listings from Idealista: {str(exc)}",
        )

    ppms = [lst.price_per_m2 for lst in listings if lst.price_per_m2]
    avg_ppm2 = int(sum(ppms) / len(ppms)) if ppms else None
    estimated = int(avg_ppm2 * request.m2) if avg_ppm2 else None

    market_transactions = build_market_transactions_mock(
        valuation_address,
        municipio,
        m2=request.m2,
        bedrooms=request.bedrooms,
        bathrooms=request.bathrooms,
        listing_avg_price_per_m2=avg_ppm2,
    )
    summary = market_transactions.summary
    margin_pct = summary.negotiation_margin_pct

    return SimpleValuationResponse(
        address=municipio.road or request.address,
        price=estimated,
        asking_price=summary.avg_asking_price,
        closing_price=summary.avg_closing_price,
        negotiation_factor=round(margin_pct / 100, 4) if margin_pct is not None else None,
        comparables_used=len(listings),
        is_mock=True,
    )


async def _build_fast_simple_valuation(request: ValuationRequest) -> SimpleValuationResponse:
    """Instant, scrape-free response built from the mock market-transactions layer.

    Geocoding via Nominatim is still needed to seed the mock with realistic
    municipio metadata, but it returns in <1s.
    """
    try:
        municipio = (
            municipio_from_resolved_address(request.selected_address)
            if request.selected_address
            else await get_municipio_from_address(request.address)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error(f"Geocoding failed (fast mode): {exc}", exc_info=True)
        raise HTTPException(status_code=502, detail="Geocoding service unavailable")

    market_transactions = build_market_transactions_mock(
        request.address,
        municipio,
        m2=request.m2,
        bedrooms=request.bedrooms,
        bathrooms=request.bathrooms,
    )
    summary = market_transactions.summary
    margin_pct = summary.negotiation_margin_pct

    return SimpleValuationResponse(
        address=municipio.road or request.address,
        price=summary.avg_closing_price,
        asking_price=summary.avg_asking_price,
        closing_price=summary.avg_closing_price,
        negotiation_factor=round(margin_pct / 100, 4) if margin_pct is not None else None,
        comparables_used=summary.total_transactions,
        is_mock=True,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
