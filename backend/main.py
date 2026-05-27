import asyncio
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
import statistics
import time
from contextlib import asynccontextmanager
from time import perf_counter

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from typing import Optional

import db
from airtable import (
    AirtableAPIError,
    AirtableConfig,
    AirtableConfigError,
    enrich_with_coach_owners,
    get_transaction,
    get_transaction_for_valuation,
    search_transactions_page,
)
from catastro import (
    CatastroByRCResult,
    address_to_catastro_query,
    fetch_property_by_reference,
    fetch_units_by_address,
    fetch_units_by_street,
)
from geocoding import (
    get_municipio_from_address,
    municipio_from_resolved_address,
    reverse_geocode,
    suggest_addresses,
)
from market import compute_appreciation, get_default_store
from models import (
    CadastralReferenceLookupRequest,
    CadastralReferenceLookupResponse,
    CadastralUnit,
    CadastralUnitsResponse,
    CoachAutoEmailPreviewResponse,
    ComparablesDataset,
    CoachAutoEmailResponse,
    CoachEmailSendRequest,
    CoachEmailSendResponse,
    CoachTransactionValuationResponse,
    DatasetRow,
    LeadInfo,
    LeadResponse,
    LeadSubmission,
    Listing,
    MarketAppreciation,
    ResolvedAddress,
    ReportPdfRenderRequest,
    SearchMetadata,
    SearchStageResult,
    SimpleValuationResponse,
    TransactionDetail,
    TransactionSearchResponse,
    TransactionSummary,
    ValuationRequest,
    ValuationResponse,
    ValuationStats,
    ValuationStatusResponse,
)
from notifications import EmailDeliveryError, send_custom_email, send_valuation_email
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

DATASET_MAX_ROWS = 5
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


async def _geocode_catastro_address(result: CatastroByRCResult) -> Optional[ResolvedAddress]:
    """Best-effort: feed the Catastro address into Nominatim so we get lat/lon
    for the valuation pipeline. Returns None when no address came back from
    Catastro or when geocoding fails — the UI can still proceed with just the
    catastro label, only without the Idealista comparables stage."""
    address = result.address
    if not address:
        return None

    def clean_catastro_part(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        # Catastro sometimes appends local abbreviations like "(CST)" for
        # Casetas; Nominatim does not know those suffixes.
        cleaned = re.sub(r"\s*\([^)]*\)\s*", " ", value)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")
        return cleaned or None

    parts: list[str] = []
    road = clean_catastro_part(address.road)
    if road:
        parts.append(road)
    if address.number:
        parts.append(address.number)
    municipality = clean_catastro_part(address.municipality) or clean_catastro_part(address.province)
    if municipality:
        parts.append(municipality)
    if address.postcode:
        parts.append(address.postcode)
    query = ", ".join(p for p in parts if p)
    if not query:
        return None

    try:
        municipio = await get_municipio_from_address(query)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Geocoding fallback for Catastro address %r failed: %s", query, exc)
        return None

    return ResolvedAddress(
        label=query,
        lat=float(municipio.lat or 0),
        lon=float(municipio.lon or 0),
        municipality=municipio.name or municipality or "",
        province=address.province or municipio.province,
        road=municipio.road or road,
        house_number=address.number,
        postcode=address.postcode or municipio.postcode,
        neighbourhood=municipio.neighbourhood,
        quarter=municipio.quarter,
        city_district=municipio.city_district,
        country="España",
        provider="catastro",
        provider_id=result.reference,
        precision="cadastral_reference",
    )


@app.post(
    "/api/catastro/by-reference",
    response_model=CadastralReferenceLookupResponse,
    summary="Resolve a property directly from its cadastral reference (14 or 20 chars)",
)
async def lookup_by_cadastral_reference(
    payload: CadastralReferenceLookupRequest,
) -> CadastralReferenceLookupResponse:
    """Alternative entry point to the valuation flow for users who already
    know their Catastro RC. Returns the matching unit(s) plus a geocoded
    `ResolvedAddress` ready to feed into `/api/lead` or `/api/valuation`."""
    try:
        result = await fetch_property_by_reference(payload.reference)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except httpx.HTTPError as exc:
        logger.error("Catastro DNPRC lookup failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="Catastro service unavailable")

    resolved_address = await _geocode_catastro_address(result)
    return CadastralReferenceLookupResponse(
        reference=result.reference,
        is_parcel=result.is_parcel,
        units=result.units,
        resolved_address=resolved_address,
        catastro_address_label=result.address.label if result.address else None,
    )


# ── Coach interface (Airtable proxy) ────────────────────────────────────────
# Single shared password gating /api/coach/* so the PAT never reaches the
# browser. Set COACH_ACCESS_PASSWORD in backend/.env. Leave it unset in local
# dev to disable the gate (the frontend sends the header anyway).


def _verify_coach_password(
    x_coach_password: Optional[str] = Header(default=None, alias="X-Coach-Password"),
) -> None:
    expected = os.environ.get("COACH_ACCESS_PASSWORD", "").strip()
    if not expected:
        return
    if not x_coach_password or x_coach_password != expected:
        raise HTTPException(status_code=401, detail="Invalid coach password")


def _airtable_config() -> AirtableConfig:
    try:
        return AirtableConfig.from_env()
    except AirtableConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


_ADDRESS_UNIT_PART_RE = re.compile(
    r"^(?:"
    r"\d{1,2}\s*(?:º|ª|°|o|a)\s*(?:[-/\s]?(?:[a-z]{1,4}|izq(?:uierda)?|dcha?|der(?:echa)?))?"
    r"|\d{1,2}\s*[-/]\s*(?:[a-z]{1,4}|izq(?:uierda)?|dcha?|der(?:echa)?)"
    r"|(?:bajo|bj|ent(?:resuelo)?|principal|pral|[aá]tico)(?:[-/\s]?[a-z0-9]+)?"
    r"|(?:planta|puerta|pta)\s+[a-z0-9ºª°-]+"
    r")$",
    re.IGNORECASE,
)


def _normalize_airtable_address_for_valuation(address: str) -> str:
    """Clean Airtable unit-level addresses before sending them to geocoding.

    Airtable may store human-readable floor/door suffixes ("2º-DR") that are
    useful to a coach but make Nominatim miss the street-level address. The
    valuation pipeline only needs the portal and locality for comparables.
    """
    parts = [part.strip() for part in address.split(",") if part.strip()]
    if not parts:
        return address.strip()

    first = re.sub(r"^\s*c\.?\s+", "Calle ", parts[0], flags=re.IGNORECASE)
    first = re.sub(r"^\s*c/\s*", "Calle ", first, flags=re.IGNORECASE)
    first = re.sub(r"^\s*cl\s+", "Calle ", first, flags=re.IGNORECASE)
    first = re.sub(r"^\s*avda?\.?\s+", "Avenida ", first, flags=re.IGNORECASE)

    cleaned = [first]
    cleaned.extend(part for part in parts[1:] if not _ADDRESS_UNIT_PART_RE.match(part))
    if not any(part.lower() in {"españa", "spain"} for part in cleaned):
        cleaned.append("España")
    return ", ".join(cleaned)


async def _resolved_address_from_transaction_reference(
    transaction: TransactionDetail,
) -> Optional[ResolvedAddress]:
    if not transaction.cadastral_reference:
        return None
    try:
        result = await fetch_property_by_reference(transaction.cadastral_reference)
    except (ValueError, httpx.HTTPError) as exc:
        logger.warning(
            "Could not resolve Airtable cadastral reference %s: %s",
            transaction.cadastral_reference,
            exc,
        )
        return None
    return await _geocode_catastro_address(result)


async def _valuation_request_from_transaction(transaction: TransactionDetail) -> ValuationRequest:
    """Build a valuation request from the normalized Airtable transaction fields."""
    missing: list[str] = []
    if not transaction.address:
        missing.append("Address")
    if not transaction.landsize_m2:
        missing.append("Landsize")
    if transaction.bedrooms is None:
        missing.append("Beds")
    if transaction.bathrooms is None:
        missing.append("Baths")
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Transaction is missing required valuation fields: {', '.join(missing)}",
        )

    selected_unit = None
    if transaction.cadastral_reference:
        selected_unit = CadastralUnit(
            cadastral_reference=transaction.cadastral_reference,
            built_area_m2=float(transaction.landsize_m2 or 0) or None,
            label=transaction.address or transaction.transaction_name,
        )

    normalized_address = _normalize_airtable_address_for_valuation(
        transaction.address or transaction.transaction_name
    )
    selected_address = await _resolved_address_from_transaction_reference(transaction)

    return ValuationRequest(
        address=normalized_address,
        m2=transaction.landsize_m2,
        bedrooms=transaction.bedrooms or 0,
        bathrooms=max(transaction.bathrooms or 1, 1),
        property_type=transaction.type,
        selected_address=selected_address,
        selected_cadastral_unit=selected_unit,
        valuation_intent="info",
    )


def _parse_settlement_date(raw: Optional[str]):
    """Parse the Airtable `Real settlement date` into a Python ``date``.

    Airtable returns ISO dates (``YYYY-MM-DD``) but sometimes also bare
    ``YYYY-MM`` or full ISO timestamps via lookup. Return ``None`` if the
    value is missing or unparseable — the caller skips appreciation in that
    case rather than crashing the whole valuation.
    """
    if not raw:
        return None
    from datetime import date

    candidates = [raw, raw[:10], f"{raw[:7]}-01" if len(raw) >= 7 else None]
    for value in candidates:
        if not value:
            continue
        try:
            return date.fromisoformat(value)
        except ValueError:
            continue
    return None


def _round_to_step(value: float, step: int = 1000) -> int:
    """Round a EUR figure to the nearest ``step`` to avoid calculator precision
    on the coach list (e.g. €151.842 → €152.000)."""
    return int(round(value / step) * step)


MUNICIPALITY_ALIASES = {
    # TF Labs stores the official Valencian form. Airtable transaction names
    # sometimes keep the older Spanish spelling.
    "moncofar": "Moncofa",
}


def _clean_municipality_guess(value: str) -> Optional[str]:
    """Clean a municipality fragment parsed from Airtable transaction text.

    The coach list precompute intentionally avoids geocoding for speed, so the
    best fallback we have is the final comma-separated segment of the address.
    Production transaction names may include unit suffixes ("u1", "u2") or
    floor/door fragments, so we trim those before matching against TF Labs.
    """
    cleaned = value.strip()
    cleaned = re.sub(r"\s+u\d+\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+unit\s+\d+\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+\d+[ºª]?\s*[A-Za-z]?\s*$", "", cleaned).strip()
    if not cleaned:
        return None
    return MUNICIPALITY_ALIASES.get(cleaned.lower(), cleaned)


def _guess_transaction_municipality(tx: TransactionSummary) -> Optional[str]:
    """Best-effort municipality extraction for list-level precomputation.

    `town_record_id` remains the preferred exact path. This parser only covers
    rows where Airtable has no Town lookup populated but the transaction name
    carries an address suffix like "<client> - <street>, <municipality>".
    """
    candidates: list[str] = []
    if tx.address:
        candidates.append(tx.address)
    if " - " in tx.transaction_name:
        candidates.append(tx.transaction_name.split(" - ", 1)[1])

    for source in candidates:
        parts = [p.strip() for p in source.split(",") if p.strip()]
        for part in reversed(parts):
            guess = _clean_municipality_guess(part)
            if guess:
                return guess
    return None


def _enrich_summary_with_appreciation(tx: TransactionSummary) -> TransactionSummary:
    """Pre-compute zone appreciation + capital gain for a list row.

    This runs the cheap TF Labs lookup only — no geocoding, no scraping. The
    coach list calls this for every row so the worklist can be ranked by
    capital gain without opening each transaction.

    Resolution chain mirrors the per-transaction valuation flow:
    - direct Airtable ``town_record_id`` (best, exact match)
    - municipality name parsed out of the transaction address (fallback)
    """
    store = get_default_store()
    if store is None:
        return tx
    settlement_date = _parse_settlement_date(tx.real_settlement_date)
    if settlement_date is None:
        return tx

    # Try town id first; fall back to a coarse name parse if absent. Airtable
    # transaction names often end in noisy suffixes like "Almassora u1" or use
    # non-official variants like "Moncofar" while TF Labs stores "Moncofa".
    municipality_guess = _guess_transaction_municipality(tx)

    town = store.resolve_town(
        airtable_record_id=tx.town_record_id,
        name=municipality_guess,
    )
    if town is None:
        return tx
    appreciation = compute_appreciation(
        store=store, town=town, settlement_date=settlement_date
    )
    if appreciation is None:
        return tx

    invested = tx.final_total_price
    area_m2 = tx.landsize_m2
    estimated_current_value: Optional[int] = None
    capital_gain: Optional[int] = None
    latest = store.latest_value(town.town_id)
    if latest is not None and area_m2:
        _latest_period, latest_eur_per_m2 = latest
        if latest_eur_per_m2 and latest_eur_per_m2 > 0:
            # Same no-scrape anchor used by `_build_no_scrape_valuation` and
            # the PDF: latest TF Labs municipal €/m2 x property surface.
            # Do not compound the original purchase price by appreciation_pct;
            # that can show a positive "gain" for assets bought far above the
            # municipal €/m2 baseline, while the report rightly shows negative.
            estimated_current_value = _round_to_step(latest_eur_per_m2 * area_m2)
    if estimated_current_value is not None and invested is not None:
        capital_gain = estimated_current_value - invested

    return tx.model_copy(
        update={
            "appreciation_pct": appreciation.pct_change,
            "appreciation_from_period": appreciation.from_period,
            "appreciation_to_period": appreciation.to_period,
            "appreciation_town_name": appreciation.town_name,
            "estimated_current_value": estimated_current_value,
            "capital_gain": capital_gain,
        }
    )


def _enrich_summaries_with_appreciation(
    transactions: list[TransactionSummary],
) -> list[TransactionSummary]:
    """Batch wrapper around :func:`_enrich_summary_with_appreciation`."""
    if not transactions:
        return transactions
    return [_enrich_summary_with_appreciation(tx) for tx in transactions]


def _compute_market_appreciation_for_transaction(
    transaction: TransactionDetail,
    request: ValuationRequest,
) -> Optional[MarketAppreciation]:
    """Resolve the property's town + settlement date and build a
    :class:`MarketAppreciation` payload.

    Resolution chain (best → worst):
    1. ``transaction.town_record_id`` — direct Airtable record id from the
       linked Town lookup.
    2. Municipality name from the geocoded address (``request.selected_address``).

    Returns ``None`` (and logs) whenever we can't produce a meaningful
    payload: missing settlement date, unmatched town, or empty series.
    """
    store = get_default_store()
    if store is None:
        return None

    settlement_date = _parse_settlement_date(transaction.real_settlement_date)
    if settlement_date is None:
        logger.info(
            "Coach appreciation: skipping — transaction %s has no Real settlement date",
            transaction.id,
        )
        return None

    municipality_name = (
        request.selected_address.municipality
        if request.selected_address and request.selected_address.municipality
        else None
    )
    province = request.selected_address.province if request.selected_address else None

    town = store.resolve_town(
        airtable_record_id=transaction.town_record_id,
        name=municipality_name,
        province_id=province,
    )
    if town is None:
        logger.info(
            "Coach appreciation: no town match for transaction %s "
            "(town_record_id=%s, municipality=%s)",
            transaction.id,
            transaction.town_record_id,
            municipality_name,
        )
        return None

    return compute_appreciation(store=store, town=town, settlement_date=settlement_date)


async def _build_no_scrape_valuation(
    request: ValuationRequest,
    transaction: Optional[TransactionDetail] = None,
) -> ValuationResponse:
    """Build a ValuationResponse WITHOUT scraping Idealista.

    Used by the coach flow when the coach opts into the "sin comparables"
    variant. We still need a credible headline number for the report, so we
    anchor it on the real TF Labs municipal €/m² series (latest observation
    for the resolved town) × ``request.m2``. The €/m² baseline is the same
    one we use for ``market_appreciation``, so the report stays internally
    consistent — no Idealista listings, but a real-data estimate.

    When the town can't be resolved or has no series data we fall back to
    leaving ``estimated_value=None`` so the renderer shows the honest
    "no estimated" hero block instead of inventing a number.
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
        logger.error("No-scrape geocoding failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="Geocoding service unavailable")

    valuation_address = (
        request.selected_address.label if request.selected_address else request.address
    )

    # Headline figure from the TF Labs municipal series. We use the latest
    # available observation rather than the settlement-period one because
    # this is a *current* valuation, not a back-calc of historical worth.
    market_eur_per_m2: Optional[int] = None
    estimated_value: Optional[int] = None
    store = get_default_store()
    town = None
    if store is not None:
        municipality_name = (
            request.selected_address.municipality
            if request.selected_address and request.selected_address.municipality
            else municipio.name
        )
        province = (
            request.selected_address.province
            if request.selected_address
            else municipio.province
        )
        # Same resolution chain as `_compute_market_appreciation_for_transaction`:
        # the Airtable Town record id is identical to ``market_towns.town_id``,
        # so when we have it we get a 100% hit. Falling back to name only is
        # brittle for bilingual municipalities (e.g. TF Labs stores Alicante as
        # "Alicante/Alacant" so the plain "Alicante" lookup misses).
        town = store.resolve_town(
            airtable_record_id=transaction.town_record_id if transaction else None,
            name=municipality_name,
            province_id=province,
        )
        if town is not None:
            latest = store.latest_value(town.town_id)
            if latest is not None:
                _period, value = latest
                if value and value > 0:
                    market_eur_per_m2 = int(round(value))
                    estimated_value = int(round(value * request.m2))

    # Confidence band — no comparables to compute σ, so we fall back to the
    # legacy ±10% so the hero still shows a range. ``confidence_method``
    # signals this clearly in the report badge.
    price_range_low = (
        int(estimated_value * 0.90) if estimated_value is not None else None
    )
    price_range_high = (
        int(estimated_value * 1.10) if estimated_value is not None else None
    )

    search_url = f"https://www.idealista.com/venta-viviendas/{quote_plus(municipio.name)}/"
    search_metadata = SearchMetadata(
        strategy="no_scrape",
        target_comparables=0,
        final_stage="market_series",
        total_duration_ms=0,
        stages=[
            SearchStageResult(
                name="market_series",
                label="TF Labs zonal €/m²",
                query=valuation_address,
                search_url=search_url,
                listings_found=0,
                duration_ms=0,
                bedrooms_mode="skipped",
                bathrooms_mode="skipped",
            )
        ],
    )

    # We still build the mock transactions block because the report's
    # "Realidad del mercado" section uses asking-vs-closing context that
    # gives the coach something to talk about. It's clearly flagged as
    # ``is_mock`` so the receiver can tell it's not real comparables.
    market_transactions = build_market_transactions_mock(
        valuation_address,
        municipio,
        m2=request.m2,
        bedrooms=request.bedrooms,
        bathrooms=request.bathrooms,
        listing_avg_price_per_m2=market_eur_per_m2,
    )

    return ValuationResponse(
        municipio=municipio,
        listings=[],
        stats=ValuationStats(
            total_comparables=0,
            avg_price=None,
            min_price=None,
            max_price=None,
            avg_price_per_m2=market_eur_per_m2,
            estimated_value=estimated_value,
            price_range_low=price_range_low,
            price_range_high=price_range_high,
            estimation_method="market_series" if estimated_value else None,
            confidence_method="flat_pct" if estimated_value else None,
        ),
        search_url=search_url,
        search_metadata=search_metadata,
        market_transactions=market_transactions,
        dataset=ComparablesDataset(
            rows=[],
            row_count=0,
            min_required=DATASET_MIN_ROWS,
            max_allowed=DATASET_MAX_ROWS,
        ),
        regression=None,
    )


async def _build_coach_mock_valuation(request: ValuationRequest) -> ValuationResponse:
    """Instant coach-only valuation for testing the Airtable/report flow.

    The live Idealista scrape can exceed two minutes; this mock keeps the
    response shape identical so results, email editing and report rendering can
    be exercised without depending on Bright Data.
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
        logger.error("Coach mock geocoding failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="Geocoding service unavailable")

    valuation_address = request.selected_address.label if request.selected_address else request.address
    market_transactions = build_market_transactions_mock(
        valuation_address,
        municipio,
        m2=request.m2,
        bedrooms=request.bedrooms,
        bathrooms=request.bathrooms,
    )
    transactions = market_transactions.transactions[:DATASET_MAX_ROWS]

    listings: list[Listing] = []
    for index, transaction in enumerate(transactions, start=1):
        price = transaction.asking_price or transaction.closing_price
        m2 = transaction.m2 or request.m2
        listings.append(
            Listing(
                title=f"Comparable mock {index} - {municipio.name}",
                price=price,
                m2=m2,
                price_per_m2=int(price / m2) if price and m2 else transaction.asking_price_per_m2,
                bedrooms=transaction.bedrooms,
                bathrooms=transaction.bathrooms,
                address=transaction.address,
                url=f"https://www.idealista.com/mock/coach-{index}",
                source_stage="coach_mock",
            )
        )

    prices = [listing.price for listing in listings if listing.price]
    ppms = [listing.price_per_m2 for listing in listings if listing.price_per_m2]
    avg_ppm2 = int(sum(ppms) / len(ppms)) if ppms else None
    baseline_estimate = int(avg_ppm2 * request.m2) if avg_ppm2 else None

    dataset = build_dataset(listings)
    regression = fit_listing_regression(dataset.rows)
    estimated, estimation_method = _choose_estimate(
        regression=regression,
        baseline_estimate=baseline_estimate,
        m2=request.m2,
        bedrooms=request.bedrooms,
        bathrooms=request.bathrooms,
    )
    price_range_low, price_range_high, confidence_method = _confidence_interval(
        estimated=estimated,
        avg_ppm2=avg_ppm2,
        ppms=ppms,
        request_m2=request.m2,
    )

    search_url = f"https://www.idealista.com/venta-viviendas/{quote_plus(municipio.name)}/"
    search_metadata = SearchMetadata(
        strategy="coach_mock",
        target_comparables=DATASET_MAX_ROWS,
        final_stage="coach_mock",
        total_duration_ms=0,
        stages=[
            SearchStageResult(
                name="coach_mock",
                label="Coach mock data",
                query=valuation_address,
                search_url=search_url,
                listings_found=len(listings),
                duration_ms=0,
                area_min=max(20, int(request.m2 * 0.8)),
                area_max=int(request.m2 * 1.2),
                bedrooms_mode="mock",
                bathrooms_mode="mock",
            )
        ],
    )

    return ValuationResponse(
        municipio=municipio,
        listings=listings,
        stats=ValuationStats(
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
        ),
        search_url=search_url,
        search_metadata=search_metadata,
        market_transactions=market_transactions,
        dataset=dataset,
        regression=regression,
    )


@app.get(
    "/api/coach/auth/check",
    summary="Fast password check for the coach UI",
    dependencies=[Depends(_verify_coach_password)],
)
async def check_coach_auth() -> dict[str, bool]:
    """Validate the shared coach password without touching Airtable.

    This keeps the login gate instant. Airtable is only queried once the
    authenticated coach lands on the transactions screen.
    """
    return {"ok": True}


@app.get(
    "/api/coach/transactions",
    response_model=TransactionSearchResponse,
    summary="Search client transactions in Airtable (coach UI)",
    dependencies=[Depends(_verify_coach_password)],
)
async def list_coach_transactions(
    q: str = Query("", description="Substring matched against Transaction Name (case-insensitive)"),
    limit: int = Query(100, ge=1, le=100),
    offset: Optional[str] = Query(
        None,
        description="Opaque Airtable pagination token returned as next_offset.",
    ),
) -> TransactionSearchResponse:
    """Search the Airtable `transactions` table from the coach UI.

    Empty `q` returns the most recent transactions (sorted by Create Date desc).

    Each row is enriched with:
      - **Coach owner** (and Account Manager) resolved against the cached
        `Team Profiles` table.
      - **Pre-computed zone appreciation** + capital gain via the TF Labs
        municipal €/m² series. This lets the frontend sort/filter the worklist
        by capital gain without opening each transaction.
    """
    config = _airtable_config()
    try:
        rows, next_offset = await search_transactions_page(
            config=config,
            query=q,
            page_size=limit,
            offset=offset,
        )
    except AirtableAPIError as exc:
        logger.error("Airtable search failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"Airtable upstream error ({exc.status_code})",
        )
    except httpx.HTTPError as exc:
        logger.error("Airtable network error: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="Airtable unreachable")

    # Coach owner enrichment is best-effort: failure shouldn't break the list.
    try:
        rows = await enrich_with_coach_owners(config=config, transactions=rows)
    except (AirtableAPIError, httpx.HTTPError) as exc:
        logger.warning("Coach owner enrichment failed: %s", exc)

    rows = _enrich_summaries_with_appreciation(rows)
    return TransactionSearchResponse(
        records=rows,
        next_offset=next_offset,
        page_size=limit,
        has_more=bool(next_offset),
    )


@app.get(
    "/api/coach/transactions/{record_id}",
    response_model=TransactionDetail,
    summary="Fetch one transaction by Airtable record id (coach UI)",
    dependencies=[Depends(_verify_coach_password)],
)
async def get_coach_transaction(record_id: str) -> TransactionDetail:
    config = _airtable_config()
    try:
        return await get_transaction(config=config, record_id=record_id)
    except AirtableAPIError as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="Transaction not found")
        logger.error("Airtable detail fetch failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"Airtable upstream error ({exc.status_code})",
        )
    except httpx.HTTPError as exc:
        logger.error("Airtable network error: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="Airtable unreachable")


@app.post(
    "/api/coach/transactions/{record_id}/valuation",
    response_model=CoachTransactionValuationResponse,
    summary="Generate a valuation from an Airtable transaction",
    dependencies=[Depends(_verify_coach_password)],
)
async def generate_coach_transaction_valuation(
    record_id: str,
    live: bool = Query(
        True,
        description="Run the live Idealista scrape. Set false for the instant coach mock.",
    ),
    include_comparables: bool = Query(
        True,
        description=(
            "When false, skip the Idealista scrape entirely and build the "
            "valuation from the TF Labs municipal €/m² series only. The "
            "report will have no per-listing comparables but a real-data "
            "headline number. Overrides ``live`` when false."
        ),
    ),
) -> CoachTransactionValuationResponse:
    """Run the existing valuation pipeline using property fields from Airtable."""
    config = _airtable_config()
    try:
        transaction = await get_transaction_for_valuation(config=config, record_id=record_id)
    except AirtableAPIError as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="Transaction not found")
        logger.error("Airtable detail fetch failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"Airtable upstream error ({exc.status_code})",
        )
    except httpx.HTTPError as exc:
        logger.error("Airtable network error: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="Airtable unreachable")

    request = await _valuation_request_from_transaction(transaction)
    if not include_comparables:
        valuation = await _build_no_scrape_valuation(request, transaction)
    elif live:
        valuation = await get_valuation(request)
    else:
        valuation = await _build_coach_mock_valuation(request)
    # Real-data zone appreciation. Failing this should never fail the whole
    # endpoint — the coach UI degrades gracefully when the block is absent.
    try:
        valuation.market_appreciation = _compute_market_appreciation_for_transaction(
            transaction, request
        )
    except Exception as exc:  # noqa: BLE001 — best effort enrichment
        logger.warning(
            "Coach appreciation failed for transaction %s: %s",
            transaction.id,
            exc,
            exc_info=True,
        )
    return CoachTransactionValuationResponse(
        transaction=transaction,
        valuation_request=request,
        valuation=valuation,
    )


def _format_period_es(period: Optional[str]) -> str:
    """Render a ``YYYY-MM`` period as 'MMM YYYY' in Spanish (for email copy)."""
    if not period or "-" not in period:
        return "—"
    try:
        year, month = period.split("-")
        month_idx = int(month)
    except ValueError:
        return period
    months = [
        "ene.", "feb.", "mar.", "abr.", "may.", "jun.",
        "jul.", "ago.", "sept.", "oct.", "nov.", "dic.",
    ]
    if not 1 <= month_idx <= 12:
        return period
    return f"{months[month_idx - 1]} {year}"


def _format_eur(value: Optional[int]) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f} €".replace(",", ".")


def _format_pct(value: Optional[float]) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value * 100:.1f}%"


def _client_first_name(transaction_name: str) -> str:
    """Pull a friendly first name out of an Airtable Transaction Name.

    Names follow the ``<Client name> - <Address>`` convention; we split on the
    separator and take the first word of the leading half. Falls back to the
    full name when the convention isn't honoured.
    """
    head = transaction_name.split(" - ")[0].strip()
    return head.split(" ")[0] if head else transaction_name


def _build_default_coach_email(
    *,
    transaction: TransactionDetail,
    valuation_request: ValuationRequest,
    valuation: ValuationResponse,
) -> tuple[str, str]:
    """Build the default subject + body for an auto-sent coach email.

    Mirrors the structure the frontend ``CoachClientReportComposer`` creates so
    a bulk-sent email reads the same as one a coach composed by hand. Keeping
    the copy on the backend lets the bulk endpoint stay stateless.
    """
    address = (
        valuation_request.selected_address.label
        if valuation_request.selected_address
        else valuation_request.address
    )
    appreciation = valuation.market_appreciation
    invested = transaction.final_total_price

    # Recommended exit band (±3% around the headline estimate, rounded to €1k).
    # Same band the frontend renders in the report. Keeps copy/numbers in sync.
    anchor = valuation.stats.estimated_value
    if anchor is not None:
        low_raw = anchor * 0.97
        high_raw = anchor * 1.03
        low_rounded = _round_to_step(low_raw)
        high_rounded = _round_to_step(high_raw)
        if high_rounded <= low_rounded:
            high_rounded = low_rounded + 1000
        recommended_band = (low_rounded, high_rounded)
    else:
        recommended_band = (None, None)

    band_text = (
        f"{_format_eur(recommended_band[0])} – {_format_eur(recommended_band[1])}"
        if recommended_band[0] is not None and recommended_band[1] is not None
        else "—"
    )

    gain_low = (
        recommended_band[0] - invested
        if recommended_band[0] is not None and invested is not None
        else None
    )
    gain_high = (
        recommended_band[1] - invested
        if recommended_band[1] is not None and invested is not None
        else None
    )
    gain_text = (
        f"{_format_eur(gain_low)} – {_format_eur(gain_high)}"
        if gain_low is not None and gain_high is not None
        else "—"
    )

    is_no_scrape = valuation.search_metadata.strategy == "no_scrape"
    source_line = (
        "Fuente del rango: TF Labs, serie municipal basada en cierres trimestrales "
        "de registradores, aplicada a la superficie del inmueble. Es una referencia "
        "de municipio, no una tasación individual; el valor final puede variar según "
        "las características de la propiedad."
        if is_no_scrape
        else "Fuente del rango: comparables activos en Idealista al momento de la valoración."
    )

    appreciation_line = (
        f"En tu zona ({appreciation.town_name}) el €/m² ha variado un "
        f"{_format_pct(appreciation.pct_change)} entre "
        f"{_format_period_es(appreciation.from_period)} y "
        f"{_format_period_es(appreciation.to_period)}."
        if appreciation
        else "Hemos cruzado los datos de tu operación con la evolución reciente del mercado."
    )

    subject = f"Tu propiedad podría haberse revalorizado — {address}"

    body_lines = [
        f"Hola {_client_first_name(transaction.transaction_name)},",
        "",
        "Soy del equipo de PropHero. Hemos preparado una estimación inicial con "
        "nuestra herramienta y vemos una posible revalorización de tu propiedad.",
        "",
        "Posible revalorización",
        appreciation_line,
        f"Rango recomendado de salida: {band_text}.",
        f"Ganancia potencial estimada vs. tu compra: {gain_text}.",
        "",
        "Qué podría significar",
        "No es una tasación oficial ni una promesa de venta; es una primera estimación "
        "que indica que puede ser un buen momento para valorar una desinversión. Si "
        "los números encajan, podrías capturar parte de esa plusvalía y estudiar la "
        "compra de otra propiedad con una estrategia más clara.",
        "",
        "Fuente",
        source_line,
        "",
        "Siguiente paso",
        "Puedes leer el informe adjunto y, si tiene sentido explorarlo, agendar una "
        "llamada gratuita con un tasador para revisar el caso concreto aquí:",
        "https://prophero.com/contacto",
        "",
        "Un saludo,",
        "PropHero",
    ]
    return subject, "\n".join(body_lines)


def _capital_gain_from_valuation(
    transaction: TransactionDetail,
    valuation: ValuationResponse,
) -> Optional[int]:
    """Capital gain at the mid-point of the recommended band (anchor +/-0%)."""

    invested = transaction.final_total_price
    if valuation.stats.estimated_value is None or invested is None:
        return None
    return int(round(valuation.stats.estimated_value - invested))


def _review_warning_for_auto_email(
    *,
    transaction: TransactionDetail,
    valuation: ValuationResponse,
    capital_gain: Optional[int],
) -> Optional[str]:
    """Flag drafts that should be read carefully before sending."""

    if not transaction.client_email:
        return "No hay email de cliente; no se puede enviar automáticamente."
    if capital_gain is not None and capital_gain <= 0:
        return "Ganancia estimada negativa o cero; revisar antes de contactar al cliente."
    appreciation = valuation.market_appreciation
    if appreciation and appreciation.pct_change <= 0:
        return "La revalorización municipal es negativa o cero; revisar el informe adjunto."
    return None


async def _prepare_auto_email_preview(record_id: str) -> CoachAutoEmailPreviewResponse:
    """Build the no-scrape valuation + email draft without sending anything."""

    config = _airtable_config()
    try:
        transaction = await get_transaction_for_valuation(config=config, record_id=record_id)
    except AirtableAPIError as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="Transaction not found")
        logger.error("Airtable detail fetch failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"Airtable upstream error ({exc.status_code})",
        )
    except httpx.HTTPError as exc:
        logger.error("Airtable network error: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="Airtable unreachable")

    valuation_request = await _valuation_request_from_transaction(transaction)
    valuation = await _build_no_scrape_valuation(valuation_request, transaction)
    # Best-effort appreciation. The email and PDF will still render without it.
    try:
        valuation.market_appreciation = _compute_market_appreciation_for_transaction(
            transaction, valuation_request
        )
    except Exception as exc:  # noqa: BLE001 - best effort enrichment
        logger.warning(
            "Auto-email preview appreciation failed for transaction %s: %s",
            transaction.id,
            exc,
            exc_info=True,
        )

    subject, body = _build_default_coach_email(
        transaction=transaction,
        valuation_request=valuation_request,
        valuation=valuation,
    )
    capital_gain = _capital_gain_from_valuation(transaction, valuation)
    test_to = os.environ.get("RESEND_TEST_TO", "").strip()
    delivered_to = test_to or transaction.client_email
    return CoachAutoEmailPreviewResponse(
        transaction_id=transaction.id,
        transaction=transaction,
        valuation_request=valuation_request,
        valuation=valuation,
        client_email=transaction.client_email,
        delivered_to=delivered_to,
        subject=subject,
        body=body,
        appreciation_pct=(
            valuation.market_appreciation.pct_change
            if valuation.market_appreciation
            else None
        ),
        capital_gain=capital_gain,
        estimated_value=valuation.stats.estimated_value,
        review_warning=_review_warning_for_auto_email(
            transaction=transaction,
            valuation=valuation,
            capital_gain=capital_gain,
        ),
    )


@app.post(
    "/api/coach/transactions/{record_id}/email/send",
    response_model=CoachEmailSendResponse,
    summary="Send an editable coach email to a transaction client",
    dependencies=[Depends(_verify_coach_password)],
)
async def send_coach_transaction_email(
    record_id: str,
    payload: CoachEmailSendRequest,
) -> CoachEmailSendResponse:
    """Send a coach-authored email via Resend.

    We fetch the transaction first so the endpoint remains scoped to a real
    Airtable record and to keep future audit/persistence hooks straightforward.
    """
    config = _airtable_config()
    try:
        transaction = await get_transaction(config=config, record_id=record_id)
        attachment_bytes: bytes | None = None
        if payload.valuation and payload.valuation_request:
            html = render_report_html(
                valuation=payload.valuation,
                request_payload=payload.valuation_request.model_dump(mode="json"),
                lead=payload.lead,
                transaction=payload.transaction or transaction,
                include_comparables=payload.include_comparables,
            )
            attachment_bytes = await generate_pdf_bytes(html)

        sent = await send_custom_email(
            to=payload.to,
            subject=payload.subject,
            body=payload.body,
            attachment_filename=(
                f"prophero-valoracion-{record_id}.pdf"
                if attachment_bytes is not None
                else None
            ),
            attachment_bytes=attachment_bytes,
        )
    except AirtableAPIError as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="Transaction not found")
        logger.error("Airtable detail fetch failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"Airtable upstream error ({exc.status_code})",
        )
    except EmailDeliveryError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return CoachEmailSendResponse(
        sent=sent,
        message="Email sent" if sent else "RESEND_API_KEY not set — email skipped in dev",
    )


@app.post(
    "/api/coach/transactions/{record_id}/email/auto-preview",
    response_model=CoachAutoEmailPreviewResponse,
    summary="Generate the default coach email + report payload without sending",
    dependencies=[Depends(_verify_coach_password)],
)
async def preview_auto_coach_transaction_email(
    record_id: str,
) -> CoachAutoEmailPreviewResponse:
    """Prepare the bulk-send draft so a coach can review copy and PDF first."""

    return await _prepare_auto_email_preview(record_id)


@app.post(
    "/api/coach/transactions/{record_id}/email/auto-send",
    response_model=CoachAutoEmailResponse,
    summary="Auto-generate + send the default coach email for one transaction",
    dependencies=[Depends(_verify_coach_password)],
)
async def auto_send_coach_transaction_email(
    record_id: str,
) -> CoachAutoEmailResponse:
    """Auto-pipeline: Airtable → no-scrape valuation → PDF → branded email.

    Used by the coach UI's bulk-send action. Each call is a self-contained
    pipeline so the frontend can fan it out in parallel with a small
    concurrency cap (3) to keep Airtable + Resend happy.

    Bulk delivery deliberately uses the **no-scrape** valuation (TF Labs
    municipal €/m² only): it's instant, deterministic, and the data the email
    leans on is the zone appreciation, not individual Idealista comparables.
    """
    preview = await _prepare_auto_email_preview(record_id)
    transaction = preview.transaction
    valuation_request = preview.valuation_request
    valuation = preview.valuation
    subject = preview.subject
    body = preview.body

    if not transaction.client_email:
        return CoachAutoEmailResponse(
            transaction_id=transaction.id,
            sent=False,
            skipped_reason="Transaction has no client email",
            client_email=None,
            subject=subject,
            appreciation_pct=preview.appreciation_pct,
            capital_gain=preview.capital_gain,
            estimated_value=preview.estimated_value,
        )

    try:
        html = render_report_html(
            valuation=valuation,
            request_payload=valuation_request.model_dump(mode="json"),
            lead=None,
            transaction=transaction,
            include_comparables=False,
        )
        attachment_bytes = await generate_pdf_bytes(html)
    except Exception as exc:  # noqa: BLE001 — surface as 502 below
        logger.error("Auto-send PDF render failed for %s: %s", record_id, exc, exc_info=True)
        raise HTTPException(status_code=502, detail=f"PDF render failed: {exc}")

    test_to = os.environ.get("RESEND_TEST_TO", "").strip()
    delivered_to = test_to or transaction.client_email
    try:
        sent = await send_custom_email(
            to=transaction.client_email,
            subject=subject,
            body=body,
            attachment_filename=f"prophero-valoracion-{record_id}.pdf",
            attachment_bytes=attachment_bytes,
        )
    except EmailDeliveryError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return CoachAutoEmailResponse(
        transaction_id=transaction.id,
        sent=sent,
        skipped_reason=None if sent else "RESEND_API_KEY not configured",
        delivered_to=delivered_to if sent else None,
        client_email=transaction.client_email,
        subject=subject,
        appreciation_pct=preview.appreciation_pct,
        capital_gain=preview.capital_gain,
        estimated_value=preview.estimated_value,
    )


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
async def post_report_pdf(
    request: ValuationRequest,
    include_comparables: bool = Query(
        True,
        description=(
            "Toggle the per-listing comparables section in the PDF. Aggregate "
            "stats (avg €/m², total count) always stay in the report."
        ),
    ),
) -> Response:
    """Run a valuation and return the PDF report as `application/pdf`.

    Useful for preview / re-download from the frontend without re-sending the
    email. We persist neither the lead nor the valuation here — that's what
    `/api/lead` is for.
    """
    valuation = await get_valuation(request)
    html = render_report_html(
        valuation=valuation,
        request_payload=request.model_dump(),
        include_comparables=include_comparables,
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


@app.post(
    "/api/report/pdf/render",
    response_class=Response,
    summary="Render a PDF from an already-computed valuation payload",
)
async def post_report_pdf_render(payload: ReportPdfRenderRequest) -> Response:
    """Return a PDF report without re-running geocoding or scraping.

    The results page already has the full ValuationResponse, so previewing or
    downloading the report should only render that snapshot to PDF.

    ``payload.include_comparables`` lets the caller pick the report variant
    (default ``True`` — full report; ``False`` — same numbers without the
    per-listing Idealista cards).
    """
    html = render_report_html(
        valuation=payload.valuation,
        request_payload=payload.valuation_request.model_dump(mode="json"),
        lead=payload.lead,
        transaction=payload.transaction,
        include_comparables=payload.include_comparables,
    )
    try:
        pdf_bytes = await generate_pdf_bytes(html)
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("PDF generation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Could not render PDF report")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="prophero-valoracion.pdf"'},
    )


# Hard ceiling for the synchronous portion of /api/lead. The full valuation
# pipeline (Bright Data scrape with CAPTCHA + detail enrichment) commonly
# runs in 40-70s but can blow past 2 min on bad Idealista days. Past this
# threshold we stop blocking the frontend, return a "pending" response, and
# finish the work in a BackgroundTask (so the user still gets the email).
LEAD_SYNC_VALUATION_TIMEOUT_S = 75.0


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


async def _retry_valuation_and_send_email(
    *,
    valuation_id: int,
    lead: LeadInfo,
    request: ValuationRequest,
    request_payload: dict,
) -> None:
    """Re-run a valuation that didn't finish synchronously.

    Used by `/api/lead` when the in-band pipeline either timed out or raised:
    the lead has been ack'd to the user as 'pending', but we still want to
    deliver the report by email. This coroutine runs without a hard deadline
    so it has all the time it needs to clear Idealista CAPTCHAs etc.
    """
    try:
        valuation = await get_valuation(request)
    except HTTPException as exc:
        logger.error(
            "Background valuation retry failed for valuation %d (HTTP %s): %s",
            valuation_id,
            exc.status_code,
            exc.detail,
        )
        _mark_valuation_failed(
            valuation_id,
            request,
            reason=f"valuation_retry_http_{exc.status_code}",
            detail=str(exc.detail),
        )
        db.mark_email_sent(valuation_id, error=f"valuation_retry_http_{exc.status_code}: {exc.detail}")
        return
    except Exception as exc:  # pylint: disable=broad-except
        logger.error(
            "Background valuation retry crashed for valuation %d: %s",
            valuation_id,
            exc,
            exc_info=True,
        )
        _mark_valuation_failed(
            valuation_id,
            request,
            reason="valuation_retry_crash",
            detail=f"{type(exc).__name__}: {exc}",
        )
        db.mark_email_sent(valuation_id, error=f"valuation_retry_crash: {type(exc).__name__}: {exc}")
        return

    # Backfill the now-completed payload onto the placeholder row so the
    # admin/SQLite view shows the real result (not the pending stub).
    try:
        db.update_valuation_response(
            valuation_id=valuation_id,
            municipio=valuation.municipio.name,
            estimated_eur=valuation.stats.estimated_value,
            response_payload=valuation.model_dump(mode="json"),
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "Could not backfill valuation %d response payload: %s",
            valuation_id,
            exc,
        )

    await _send_report_in_background(
        valuation_id=valuation_id,
        lead=lead,
        valuation=valuation,
        request_payload=request_payload,
    )


def _placeholder_response_payload(
    request: ValuationRequest, *, reason: str
) -> dict[str, object]:
    """Stub `response_json` used when the synchronous valuation didn't finish.

    Keeps the DB row well-formed (no NULL response_json) and gives ops a
    quick way to spot pending rows in `sqlite3` without parsing JSON."""
    return {
        "status": "pending",
        "reason": reason,
        "request": request.model_dump(mode="json"),
    }


def _mark_valuation_failed(
    valuation_id: int,
    request: ValuationRequest,
    *,
    reason: str,
    detail: str | None = None,
) -> None:
    """Replace a pending placeholder with a 'failed' marker so the frontend
    polling loop sees the failure immediately instead of polling forever
    against a row whose `response_json` would otherwise remain 'pending'.

    The GET /api/valuations/{id}/status endpoint maps `response_json.status
    == 'failed'` to a PollOutcome of `{ kind: 'failed' }`, which the UI uses
    to surface a clear error / email-fallback path."""
    payload: dict[str, object] = {
        "status": "failed",
        "reason": reason,
        "request": request.model_dump(mode="json"),
    }
    if detail:
        payload["detail"] = detail
    try:
        db.update_valuation_response(
            valuation_id=valuation_id,
            municipio=None,
            estimated_eur=None,
            response_payload=payload,
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "Could not mark valuation %d as failed: %s", valuation_id, exc
        )


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

    Happy path (status='ready'):
      1. Persist the lead in SQLite.
      2. Run the full valuation with a `LEAD_SYNC_VALUATION_TIMEOUT_S` ceiling.
      3. Persist the valuation tied to the lead.
      4. Schedule PDF render + email send as a BackgroundTask.
      5. Return with the valuation payload.

    Slow / failed path (status='pending'):
      - The lead is still persisted (we never lose contact info).
      - A placeholder valuation row is inserted.
      - A BackgroundTask retries the full pipeline and sends the email when
        ready.
      - The user gets an instant 200 with `valuation: null` so the UI can
        show a "we'll email you" success state instead of an ERROR banner.

    This is the fix for the "se queda trabado / aparece ERROR al generar el
    reporte" feedback — slow scrapes no longer surface as failures to the
    user, they degrade gracefully into the asynchronous path.
    """
    request_payload = submission.valuation_request.model_dump(mode="json")
    email_scheduled = bool(os.environ.get("RESEND_API_KEY"))

    lead_id = db.insert_lead(
        full_name=submission.lead.full_name,
        email=submission.lead.email,
        phone=submission.lead.phone,
    )
    logger.info("Lead persisted id=%d (%s)", lead_id, submission.lead.email)

    valuation: Optional[ValuationResponse] = None
    failure_reason: Optional[str] = None
    try:
        valuation = await asyncio.wait_for(
            get_valuation(submission.valuation_request),
            timeout=LEAD_SYNC_VALUATION_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        failure_reason = "sync_timeout"
        logger.warning(
            "Lead %d valuation exceeded %.0fs — handing off to background retry",
            lead_id,
            LEAD_SYNC_VALUATION_TIMEOUT_S,
        )
    except HTTPException as exc:
        failure_reason = f"http_{exc.status_code}"
        logger.warning(
            "Lead %d valuation failed (HTTP %s: %s) — handing off to background retry",
            lead_id,
            exc.status_code,
            exc.detail,
        )
    except Exception as exc:  # pylint: disable=broad-except
        failure_reason = f"crash_{type(exc).__name__}"
        logger.error(
            "Lead %d valuation crashed (%s) — handing off to background retry",
            lead_id,
            exc,
            exc_info=True,
        )

    if valuation is not None:
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
            status="ready",
            email_scheduled=email_scheduled,
        )

    # Pending path: persist a stub and hand the work to the background.
    valuation_id = db.insert_valuation(
        lead_id=lead_id,
        request=submission.valuation_request,
        municipio=None,
        estimated_eur=None,
        response_payload=_placeholder_response_payload(
            submission.valuation_request, reason=failure_reason or "unknown"
        ),
    )
    logger.info(
        "Pending valuation persisted id=%d (reason=%s) — scheduling retry",
        valuation_id,
        failure_reason,
    )

    background_tasks.add_task(
        _retry_valuation_and_send_email,
        valuation_id=valuation_id,
        lead=submission.lead,
        request=submission.valuation_request,
        request_payload=request_payload,
    )

    return LeadResponse(
        lead_id=lead_id,
        valuation_id=valuation_id,
        valuation=None,
        status="pending",
        email_scheduled=email_scheduled,
        message=(
            "Estamos terminando de analizar tu propiedad. Te enviaremos el informe completo "
            "por email en unos minutos."
        ),
    )


@app.get(
    "/api/valuations/{valuation_id}/status",
    response_model=ValuationStatusResponse,
    summary="Poll a valuation's status (used by the frontend after /api/lead returns 'pending')",
)
async def get_valuation_status(valuation_id: int) -> ValuationStatusResponse:
    """Return the current state of a valuation row.

    The frontend calls this every few seconds after `/api/lead` returned
    `status='pending'` so it can keep the loading spinner alive and
    transition to the results dashboard the moment the background retry
    finishes — instead of dead-ending on the "we'll email you" screen.

    Status mapping:
      - response_json carries our pending stub (`status='pending'`) → 'pending'
      - response_json carries `status='failed'` (future use)            → 'failed'
      - response_json parses as a ValuationResponse                     → 'ready'
      - response_json is malformed (shouldn't happen)                   → 'failed'
    """
    record = db.get_valuation(valuation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Valuation not found")

    payload = record.response_json or {}
    pending_status = (
        payload.get("status") if isinstance(payload, dict) else None
    )

    if pending_status == "pending":
        return ValuationStatusResponse(
            valuation_id=valuation_id,
            status="pending",
            valuation=None,
        )

    if pending_status == "failed":
        return ValuationStatusResponse(
            valuation_id=valuation_id,
            status="failed",
            valuation=None,
            error=payload.get("reason") if isinstance(payload, dict) else None,
        )

    # Otherwise the response_json should be a serialized ValuationResponse —
    # parse it back to validate the shape before handing it to the client.
    try:
        valuation = ValuationResponse.model_validate(payload)
    except ValidationError as exc:
        logger.error(
            "Valuation %d response_json failed to validate: %s",
            valuation_id,
            exc,
        )
        return ValuationStatusResponse(
            valuation_id=valuation_id,
            status="failed",
            valuation=None,
            error="stored_payload_invalid",
        )

    return ValuationStatusResponse(
        valuation_id=valuation_id,
        status="ready",
        valuation=valuation,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
