import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
import statistics
import time
from contextlib import asynccontextmanager
from time import perf_counter

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from typing import Optional

import db
from catastro import address_to_catastro_query, fetch_units_by_address, fetch_units_by_street
from geocoding import (
    get_municipio_from_address,
    municipio_from_resolved_address,
    reverse_geocode,
    suggest_addresses,
)
from models import (
    CadastralUnit,
    CadastralUnitsResponse,
    ComparablesDataset,
    DatasetRow,
    LeadInfo,
    LeadResponse,
    LeadSubmission,
    Listing,
    ResolvedAddress,
    SimpleValuationResponse,
    ValuationRequest,
    ValuationResponse,
    ValuationStats,
)
from notifications import EmailDeliveryError, send_valuation_email
from report.pdf import generate_pdf_bytes
from report.renderer import render_report_html
from scraping import scrape_idealista_listings
from valuation import (
    build_market_transactions_mock,
    fit_listing_regression,
    predict_from_regression,
)

# ── Estimation tuning knobs ────────────────────────────────────────────────
# Minimum sample size to trust the OLS regression for the headline estimate.
OLS_MIN_SAMPLE_SIZE = 6
# Minimum in-sample R² to accept the OLS estimate as the headline figure.
OLS_MIN_R_SQUARED = 0.5
# Reject the OLS estimate when it deviates from the simple `avg_ppm² × m²`
# baseline by more than this factor (sanity check against pathological fits
# on small/noisy samples).
OLS_VS_BASELINE_MAX_DEVIATION = 0.5  # 50%
# Floor for the honest confidence interval (so we never report 0 € as the low).
CI_FLOOR_EUR = 0

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _cors_origins() -> list[str]:
    """Explicit origins in production (CORS_ORIGINS). Local dev defaults to ['*']."""
    raw = os.environ.get("CORS_ORIGINS", "").strip()
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    if os.environ.get("HV_ENV") == "production":
        logger.warning(
            "HV_ENV=production but CORS_ORIGINS is unset — browser requests from Vercel will be blocked"
        )
        return []
    return ["*"]

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


def _choose_estimate(
    *,
    regression,
    baseline_estimate: Optional[int],
    m2: int,
    bedrooms: int,
    bathrooms: int,
) -> tuple[Optional[int], Optional[str]]:
    """Pick between the OLS prediction and the simple avg_ppm² × m² baseline.

    OLS wins only if all of these hold:
      - regression was produced
      - rank is full (no underdetermined system)
      - sample size ≥ OLS_MIN_SAMPLE_SIZE
      - in-sample R² ≥ OLS_MIN_R_SQUARED
      - prediction is finite, positive, and within
        OLS_VS_BASELINE_MAX_DEVIATION of the baseline (sanity check against
        pathological fits on noisy samples)

    Otherwise we fall back to `avg_ppm² × m²`. If neither path produces a
    number, we return (None, None) and let the frontend show the "no estimate"
    state honestly.
    """
    if regression is None:
        return baseline_estimate, ("avg_ppm2" if baseline_estimate else None)

    if (
        regression.is_underdetermined
        or regression.r_squared is None
        or regression.r_squared < OLS_MIN_R_SQUARED
        or regression.sample_size < OLS_MIN_SAMPLE_SIZE
    ):
        logger.info(
            "OLS rejected (n=%d, R²=%s, underdet=%s) → using avg_ppm² baseline",
            regression.sample_size,
            f"{regression.r_squared:.3f}" if regression.r_squared is not None else "n/a",
            regression.is_underdetermined,
        )
        return baseline_estimate, ("avg_ppm2" if baseline_estimate else None)

    ols_estimate = predict_from_regression(
        regression, m2=m2, bedrooms=bedrooms, bathrooms=bathrooms
    )
    if ols_estimate is None:
        return baseline_estimate, ("avg_ppm2" if baseline_estimate else None)

    if baseline_estimate:
        deviation = abs(ols_estimate - baseline_estimate) / baseline_estimate
        if deviation > OLS_VS_BASELINE_MAX_DEVIATION:
            logger.warning(
                "OLS prediction (%s) deviates %.0f%% from baseline (%s) → using baseline",
                f"{ols_estimate:,}",
                deviation * 100,
                f"{baseline_estimate:,}",
            )
            return baseline_estimate, "avg_ppm2"

    logger.info(
        "Using OLS estimate %s (R²=%.3f, n=%d)",
        f"{ols_estimate:,}",
        regression.r_squared,
        regression.sample_size,
    )
    return ols_estimate, "ols_lstsq"


def _confidence_interval(
    *,
    estimated: Optional[int],
    avg_ppm2: Optional[int],
    ppms: list[int],
    request_m2: int,
) -> tuple[Optional[int], Optional[int], Optional[str]]:
    """Build a confidence interval grounded in the dispersion of comparables.

    With ≥3 comparables we report `(avg_ppm² ± 1σ) × m²` — a wider range when
    the market is heterogeneous, narrower when listings agree. With fewer
    samples (or no avg) we fall back to the legacy ±10% flat band so the UI
    always has something to display.

    Returns `(low, high, method)` where method ∈ {'sample_std', 'flat_pct', None}.
    """
    if estimated is None:
        return None, None, None

    if avg_ppm2 and len(ppms) >= 3:
        try:
            std_ppm2 = statistics.stdev(ppms)
        except statistics.StatisticsError:
            std_ppm2 = 0.0
        low = max(CI_FLOOR_EUR, int((avg_ppm2 - std_ppm2) * request_m2))
        high = int((avg_ppm2 + std_ppm2) * request_m2)
        if high > low:
            return low, high, "sample_std"

    # Fallback: legacy ±10% so we never ship without a range.
    return (
        int(estimated * 0.90),
        int(estimated * 1.10),
        "flat_pct",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("House Valuation API starting up")
    db_path_env = os.environ.get("HV_DB_PATH")
    db.init_db(path=db_path_env if db_path_env else None)
    yield
    logger.info("House Valuation API shutting down")


app = FastAPI(
    title="House Valuation API",
    description="MVP — estimates your home value using real-time Idealista listings",
    version="0.1.0",
    lifespan=lifespan,
)

_cors = _cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors,
    allow_credentials="*" not in _cors,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Legacy local path: serve Vite source only when present (not in production Docker image).
_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
_LEGACY_INDEX = _FRONTEND_DIR / "index.html"
if _LEGACY_INDEX.is_file():
    app.mount("/static", StaticFiles(directory=str(_FRONTEND_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        return FileResponse(str(_LEGACY_INDEX))


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


@app.get("/api/catastro/units", response_model=list[CadastralUnit])
async def list_cadastral_units(
    province: str = Query(..., min_length=1),
    municipality: str = Query(..., min_length=1),
    road: str = Query(..., min_length=1),
    number: str = Query(..., min_length=1),
    road_type: str = Query("CL", min_length=1, max_length=5),
):
    """List Catastro units (escalera/planta/puerta) at a street number."""
    try:
        return await fetch_units_by_street(
            province=province.strip().upper(),
            municipality=municipality.strip().upper(),
            road_type=road_type.strip().upper(),
            road=road.strip().upper(),
            number=number.strip(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except httpx.HTTPError as exc:
        logger.error("Catastro units lookup failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="Catastro service unavailable")


@app.post("/api/catastro/units/lookup", response_model=CadastralUnitsResponse)
async def lookup_cadastral_units(address: ResolvedAddress):
    """
    Resolve a geocoded address to Catastro units at that street number.
    Used after address autocomplete to disambiguate floor/door (Fotocasa-style).
    """
    try:
        query = address_to_catastro_query(address)
        units = await fetch_units_by_address(address)
        return CadastralUnitsResponse(
            units=units,
            query={
                "province": query.province,
                "municipality": query.municipality,
                "road_type": query.road_type,
                "road": query.road,
                "number": query.number,
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except httpx.HTTPError as exc:
        logger.error("Catastro lookup failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="Catastro service unavailable")


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
    baseline_estimate = int(avg_ppm2 * request.m2) if avg_ppm2 else None

    dataset = build_dataset(listings)
    log_dataset(dataset)

    regression = fit_listing_regression(dataset.rows)

    # --- Choose headline estimate: OLS prediction or the avg_ppm² fallback. ---
    estimated, estimation_method = _choose_estimate(
        regression=regression,
        baseline_estimate=baseline_estimate,
        m2=request.m2,
        bedrooms=request.bedrooms,
        bathrooms=request.bathrooms,
    )

    # --- Honest confidence interval: ±1σ of comparables' €/m², not a flat ±10%. ---
    price_range_low, price_range_high, confidence_method = _confidence_interval(
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
    market_transactions = build_market_transactions_mock(
        valuation_address,
        municipio,
        m2=request.m2,
        bedrooms=request.bedrooms,
        bathrooms=request.bathrooms,
        listing_avg_price_per_m2=avg_ppm2,
    )

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


@app.post(
    "/api/report/pdf",
    response_class=Response,
    summary="Render a PDF of the valuation report for the given request payload",
)
async def post_report_pdf(request: ValuationRequest) -> Response:
    """Run a valuation and return the PDF report as `application/pdf`.

    Useful for preview / re-download from the frontend without re-sending the
    email. We persist neither the lead nor the valuation here — that's what
    `/api/lead` is for.
    """
    valuation = await get_valuation(request)
    html = render_report_html(
        valuation=valuation,
        request_payload=request.model_dump(),
    )
    try:
        pdf_bytes = await generate_pdf_bytes(html)
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("PDF generation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Could not render PDF report")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="prophero-valoracion.pdf"'},
    )


async def _send_report_in_background(
    *,
    valuation_id: int,
    lead: LeadInfo,
    valuation: ValuationResponse,
    request_payload: dict,
) -> None:
    """Render the PDF and send the email. Errors are caught and persisted on
    the valuation row so we don't crash the BackgroundTask. The user already
    got their HTTP 200 — the worst case is they get the report later (or we
    investigate the email_error column)."""
    try:
        html = render_report_html(
            valuation=valuation,
            request_payload=request_payload,
            lead=lead,
        )
        pdf_bytes = await generate_pdf_bytes(html)
        await send_valuation_email(lead=lead, valuation=valuation, pdf_bytes=pdf_bytes)
        db.mark_email_sent(valuation_id)
    except EmailDeliveryError as exc:
        logger.error("Email delivery failed for valuation %d: %s", valuation_id, exc)
        db.mark_email_sent(valuation_id, error=str(exc))
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Background report send failed for valuation %d: %s", valuation_id, exc, exc_info=True)
        db.mark_email_sent(valuation_id, error=f"{type(exc).__name__}: {exc}")


@app.post(
    "/api/lead",
    response_model=LeadResponse,
    summary="Submit lead + valuation, persist both, and email the report (PDF) in background",
)
async def post_lead(
    submission: LeadSubmission,
    background_tasks: BackgroundTasks,
) -> LeadResponse:
    """Single-shot endpoint for the frontend submission flow.

    Pipeline (synchronous portion, returned to client):
      1. Persist the lead in SQLite.
      2. Run the full valuation (this is the slow part — same as /api/valuation).
      3. Persist the valuation tied to the lead.
      4. Schedule the PDF render + email send as a BackgroundTask.
      5. Return immediately with the valuation payload + ack.

    Step 4 runs after the response is sent. The frontend can show "Te enviamos
    el reporte a {email}" right away without waiting on Playwright + Resend.
    """
    request_payload = submission.valuation_request.model_dump(mode="json")

    lead_id = db.insert_lead(
        full_name=submission.lead.full_name,
        email=submission.lead.email,
        phone=submission.lead.phone,
    )
    logger.info("Lead persisted id=%d (%s)", lead_id, submission.lead.email)

    valuation = await get_valuation(submission.valuation_request)

    valuation_id = db.insert_valuation(
        lead_id=lead_id,
        request=submission.valuation_request,
        municipio=valuation.municipio.name,
        estimated_eur=valuation.stats.estimated_value,
        response_payload=valuation.model_dump(mode="json"),
    )
    logger.info(
        "Valuation persisted id=%d intent=%s rc=%s",
        valuation_id,
        submission.valuation_request.valuation_intent,
        (
            submission.valuation_request.selected_cadastral_unit.cadastral_reference
            if submission.valuation_request.selected_cadastral_unit
            else None
        ),
    )

    email_scheduled = bool(os.environ.get("RESEND_API_KEY"))
    background_tasks.add_task(
        _send_report_in_background,
        valuation_id=valuation_id,
        lead=submission.lead,
        valuation=valuation,
        request_payload=request_payload,
    )

    return LeadResponse(
        lead_id=lead_id,
        valuation_id=valuation_id,
        valuation=valuation,
        email_scheduled=email_scheduled,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
