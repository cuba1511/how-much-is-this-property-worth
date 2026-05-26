from pydantic import BaseModel, Field
from typing import Any, Literal, Optional

ValuationIntent = Literal["sell", "buy", "rent_out", "rent", "info"]
SellReason = Literal[
    "upgrade", "downsize", "investment", "inheritance", "relocation", "other"
]
SellTimeline = Literal["asap", "3_months", "6_months", "12_months", "flexible"]
RentTimeline = Literal["asap", "1_3_months", "3_6_months", "over_6_months"]


class ResolvedAddress(BaseModel):
    label: str
    lat: float
    lon: float
    municipality: str
    province: Optional[str] = None
    road: Optional[str] = None
    house_number: Optional[str] = None
    postcode: Optional[str] = None
    neighbourhood: Optional[str] = None
    quarter: Optional[str] = None
    city_district: Optional[str] = None
    country: Optional[str] = None
    provider: str = "nominatim"
    provider_id: Optional[str] = None
    precision: Optional[str] = None


class CadastralUnit(BaseModel):
    """One registered property at a street number (Catastro Consulta_DNPLOC)."""

    cadastral_reference: str
    block: Optional[str] = None
    staircase: Optional[str] = None
    floor: Optional[str] = None
    door: Optional[str] = None
    built_area_m2: Optional[float] = None
    label: str = Field(..., description="Human-readable unit label for UI")


class CadastralUnitsResponse(BaseModel):
    units: list[CadastralUnit]
    query: dict[str, str] = Field(
        ...,
        description="Normalized Catastro query (province, municipality, road_type, road, number)",
    )


class CadastralReferenceLookupRequest(BaseModel):
    """Payload for POST /api/catastro/by-reference."""

    reference: str = Field(
        ...,
        min_length=1,
        max_length=40,
        description="Catastro reference. 14 chars = parcela (returns all units), 20 chars = inmueble.",
    )


class CadastralReferenceLookupResponse(BaseModel):
    """Outcome of resolving a cadastral reference straight to a property.

    `resolved_address` is geocoded from the Catastro-supplied address so the
    rest of the valuation pipeline (Idealista scraper, municipio metadata)
    can run exactly like the address-search flow.
    """

    reference: str
    is_parcel: bool = Field(
        ...,
        description="True when the user supplied a 14-char parcela RC — the UI should ask them to pick one of the units.",
    )
    units: list[CadastralUnit]
    resolved_address: Optional["ResolvedAddress"] = None
    catastro_address_label: Optional[str] = Field(
        None,
        description="Raw address string from Catastro (kept for display when geocoding fails).",
    )


class PropertyFeatures(BaseModel):
    pool: bool = False
    terrace: bool = False
    elevator: bool = False
    parking: bool = False


class ValuationRequest(BaseModel):
    address: str = Field(..., description="Full address of the property")
    m2: int = Field(..., gt=0, description="Surface area in square meters")
    bedrooms: int = Field(..., ge=0, description="Number of bedrooms")
    bathrooms: int = Field(..., ge=1, description="Number of bathrooms")
    property_type: Optional[str] = Field(None, description="Property type (casa, piso, etc.)")
    property_condition: Optional[str] = Field(None, description="Property condition (obra_nueva, buen_estado, a_reformar)")
    features: Optional[PropertyFeatures] = None
    selected_address: Optional[ResolvedAddress] = None
    selected_cadastral_unit: Optional["CadastralUnit"] = None
    valuation_intent: Optional[ValuationIntent] = Field(
        None, description="Why the user requested a valuation (Fotocasa-style intent step)"
    )
    sell_reason: Optional[SellReason] = Field(
        None, description="Required when valuation_intent is sell"
    )
    sell_timeline: Optional[SellTimeline] = Field(
        None, description="Required when valuation_intent is sell"
    )
    rent_timeline: Optional[RentTimeline] = Field(
        None, description="Required when valuation_intent is rent_out"
    )


class LeadInfo(BaseModel):
    """End-user contact captured at submission time."""

    full_name: str = Field(..., min_length=1, max_length=120)
    email: str = Field(..., min_length=3, max_length=200)
    phone: str = Field(..., min_length=4, max_length=40)


class LeadSubmission(BaseModel):
    """Payload for POST /api/lead — bundles lead + valuation request together
    so the frontend can submit once and have the backend orchestrate everything
    (valuation → PDF → email → persistence)."""

    lead: LeadInfo
    valuation_request: ValuationRequest


class ReportPdfRenderRequest(BaseModel):
    """Payload for rendering a PDF from an already-computed valuation.

    Used by the results page preview/download flow so opening the PDF does not
    run the scraper a second time.

    ``include_comparables`` toggles the per-listing comparables section in the
    rendered report. Defaults to ``True`` so existing callers keep getting the
    full report; the frontend selector flips it off when the user prefers a
    cleaner deliverable without the Idealista cards.
    """

    valuation: "ValuationResponse"
    valuation_request: ValuationRequest
    lead: Optional[LeadInfo] = None
    transaction: Optional["TransactionDetail"] = None
    include_comparables: bool = True


LeadValuationStatus = Literal["ready", "pending", "failed"]


class LeadResponse(BaseModel):
    """Acknowledgement returned to the frontend.

    Two-mode contract:
      - status='ready'  → valuation finished in time, payload is in `valuation`.
                          Frontend can render the results page immediately.
      - status='pending' → valuation didn't finish synchronously (scraper timeout,
                          Idealista CAPTCHA storm, etc.). The lead is saved and
                          a background task will retry the full pipeline and
                          email the report when it's ready. Frontend shows a
                          friendly "we'll email you" success screen instead of
                          an error banner — this is the case that used to look
                          like a broken/stuck submit.
      - status='failed' → reserved for future use (currently we always retry).
    """

    lead_id: int
    valuation_id: int
    valuation: Optional["ValuationResponse"] = None
    status: LeadValuationStatus = "ready"
    email_scheduled: bool = Field(
        ...,
        description="True when an email send was queued. False when RESEND_API_KEY is unset (dev mode).",
    )
    message: Optional[str] = Field(
        None,
        description="Human-readable hint for the user. Populated when status != 'ready'.",
    )


ValuationPollStatus = Literal["ready", "pending", "failed"]


class ValuationStatusResponse(BaseModel):
    """Polling contract for GET /api/valuations/{id}/status.

    Used by the frontend to keep the loading spinner alive after `/api/lead`
    returned status='pending': we poll this endpoint every few seconds until
    the background retry finishes the valuation, then transition the UI to
    the results dashboard instead of the "we'll email you" fallback.
    """

    valuation_id: int
    status: ValuationPollStatus = Field(
        ...,
        description=(
            "'ready' = `valuation` is populated. "
            "'pending' = background retry still running. "
            "'failed' = background retry crashed; check `error`."
        ),
    )
    valuation: Optional["ValuationResponse"] = None
    error: Optional[str] = Field(
        None,
        description=(
            "Populated when status='failed'. Comes from the persisted "
            "`response_json.reason` or the email_error column."
        ),
    )


# ---------------------------------------------------------------------------
# SQLite row models (see backend/db.py — denormalized columns + JSON snapshots)
# ---------------------------------------------------------------------------


class LeadRecord(BaseModel):
    """Persisted lead from POST /api/lead."""

    id: int
    full_name: str
    email: str
    phone: str
    created_at: str


class ValuationRecord(BaseModel):
    """Persisted valuation: queryable columns plus full request/response JSON."""

    id: int
    lead_id: Optional[int] = None
    address: str
    municipio: Optional[str] = None
    estimated_eur: Optional[int] = None
    valuation_intent: Optional[ValuationIntent] = None
    sell_reason: Optional[SellReason] = None
    sell_timeline: Optional[SellTimeline] = None
    rent_timeline: Optional[RentTimeline] = None
    cadastral_reference: Optional[str] = None
    property_type: Optional[str] = None
    property_condition: Optional[str] = None
    m2: Optional[int] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    request_json: dict[str, Any] = Field(
        ...,
        description="Full ValuationRequest snapshot (includes selected_address, features, etc.)",
    )
    response_json: dict[str, Any] = Field(..., description="Full ValuationResponse snapshot")
    email_sent: bool = False
    email_error: Optional[str] = None
    created_at: str


class MunicipioInfo(BaseModel):
    name: str
    slug: str
    province: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    road: Optional[str] = None
    neighbourhood: Optional[str] = None
    quarter: Optional[str] = None
    city_district: Optional[str] = None
    postcode: Optional[str] = None


class Listing(BaseModel):
    title: str
    price: Optional[int] = None
    m2: Optional[int] = None
    price_per_m2: Optional[int] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    address: Optional[str] = None
    url: str
    image_url: Optional[str] = None
    floor: Optional[str] = None
    floor_number: Optional[int] = None
    source_stage: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    condition: Optional[str] = None
    has_elevator: Optional[bool] = None
    has_terrace: Optional[bool] = None
    has_pool: Optional[bool] = None
    has_garage: Optional[bool] = None
    has_garden: Optional[bool] = None
    has_storage_room: Optional[bool] = None
    has_air_conditioning: Optional[bool] = None


class DatasetRow(BaseModel):
    listing_url: str
    metros: Optional[int] = None
    precio: Optional[int] = None
    habitaciones: Optional[int] = None
    banos: Optional[int] = None


class ComparablesDataset(BaseModel):
    columns: list[str] = Field(
        default_factory=lambda: [
            "listing_url",
            "metros",
            "precio",
            "habitaciones",
            "banos",
        ]
    )
    rows: list[DatasetRow] = Field(default_factory=list)
    row_count: int = 0
    min_required: int = 3
    max_allowed: int = 10


class ValuationStats(BaseModel):
    total_comparables: int
    avg_price: Optional[int] = None
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    avg_price_per_m2: Optional[int] = None
    estimated_value: Optional[int] = None
    price_range_low: Optional[int] = None
    price_range_high: Optional[int] = None
    estimation_method: Optional[str] = Field(
        None,
        description=(
            "How estimated_value was produced. One of: 'ols_lstsq' (OLS regression "
            "on m²/hab/baños), 'avg_ppm2' (fallback when regression is unreliable), "
            "or None when no estimate could be produced."
        ),
    )
    confidence_method: Optional[str] = Field(
        None,
        description=(
            "How price_range_low/high were derived. 'sample_std' = ±1σ of "
            "comparables' €/m²; 'flat_pct' = legacy ±10% heuristic."
        ),
    )


class RegressionCoefficient(BaseModel):
    feature: str
    label: str
    kind: str  # "intercept" | "continuous"
    unit_label: Optional[str] = None
    coefficient: float


class RegressionResult(BaseModel):
    method: str = "ols_lstsq"
    coefficients: list[RegressionCoefficient] = Field(default_factory=list)
    sample_size: int
    feature_count: int
    is_underdetermined: bool
    r_squared: Optional[float] = None
    alpha: Optional[float] = None
    notes: Optional[str] = None


class MarketTransactionChartPoint(BaseModel):
    label: str
    asking_price: Optional[int] = None
    closing_price: Optional[int] = None
    negotiation_margin_pct: Optional[float] = None


class MarketTransaction(BaseModel):
    id: str
    address: Optional[str] = None
    m2: Optional[int] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    asking_price: Optional[int] = None
    closing_price: Optional[int] = None
    asking_price_per_m2: Optional[int] = None
    closing_price_per_m2: Optional[int] = None
    negotiation_margin_pct: Optional[float] = None
    close_date: Optional[str] = None
    days_on_market: Optional[int] = None
    source: str
    distance_m: Optional[int] = None


class MarketTransactionsSummary(BaseModel):
    total_transactions: int
    avg_asking_price: Optional[int] = None
    avg_closing_price: Optional[int] = None
    avg_asking_price_per_m2: Optional[int] = None
    avg_closing_price_per_m2: Optional[int] = None
    asking_vs_closing_gap_pct: Optional[float] = None
    negotiation_margin_pct: Optional[float] = None
    sample_size: int
    chart_series: list[MarketTransactionChartPoint] = Field(default_factory=list)


class MarketTransactions(BaseModel):
    summary: MarketTransactionsSummary
    transactions: list[MarketTransaction] = Field(default_factory=list)


class MarketAppreciation(BaseModel):
    """Municipal €/m² appreciation between a settlement date and the latest
    observation in the TF Labs price series.

    Used by the coach investor report to show "how much has the zone
    appreciated since the property was bought", as a real-data alternative
    to the comparables-derived capital gain.
    """

    town_id: Optional[str] = Field(
        None,
        description="Airtable record id for the municipality in the TF Labs source.",
    )
    town_name: str = Field(..., description="Spanish municipality name from the dataset.")
    ine_code: Optional[str] = Field(None, description="5-digit INE municipal code.")

    settlement_date: str = Field(
        ...,
        description="ISO date used as acquisition anchor (`Real settlement date` in Airtable).",
    )
    from_period: str = Field(..., description="YYYY-MM the baseline value was taken from.")
    from_eur_per_m2: float = Field(..., description="Median €/m² at the settlement period.")
    to_period: str = Field(..., description="YYYY-MM of the most recent observation.")
    to_eur_per_m2: float = Field(..., description="Median €/m² at the most recent period.")

    pct_change: float = Field(
        ...,
        description="Total appreciation as a decimal (e.g. 0.124 = +12.4%) between the two periods.",
    )
    annualized_pct_change: Optional[float] = Field(
        None,
        description="Compounded annual appreciation, populated when the holding period ≥ 12 months.",
    )
    months_elapsed: int = Field(
        ..., description="Months between `from_period` and `to_period`."
    )

    sample_quality: Literal["exact", "nearest_available"] = Field(
        "exact",
        description="'exact' when the settlement month was found in the series; "
        "'nearest_available' when we fell back to the closest earlier period.",
    )
    resolution_strategy: Literal["airtable_town_id", "ine_code", "name_match"] = Field(
        ...,
        description="How we matched the property to a municipality row.",
    )


class SearchStageResult(BaseModel):
    name: str
    label: str
    query: str
    search_url: str
    listings_found: int
    duration_ms: int
    area_min: Optional[int] = None
    area_max: Optional[int] = None
    bedrooms_mode: str
    bathrooms_mode: str


class SearchMetadata(BaseModel):
    strategy: str
    target_comparables: int
    final_stage: str
    total_duration_ms: int
    stages: list[SearchStageResult]


class ValuationResponse(BaseModel):
    municipio: MunicipioInfo
    listings: list[Listing]
    stats: ValuationStats
    search_url: str
    search_metadata: SearchMetadata
    market_transactions: Optional[MarketTransactions] = None
    market_appreciation: Optional[MarketAppreciation] = Field(
        None,
        description=(
            "Real-data zone appreciation since the property was acquired. "
            "Populated only when we know a settlement date (today: coach flow only)."
        ),
    )
    dataset: Optional[ComparablesDataset] = None
    regression: Optional[RegressionResult] = None


class TransactionSummary(BaseModel):
    """Trimmed Airtable transaction row for the coach search results list.

    Lookup fields from Airtable (arrays) are pre-flattened into scalars so the
    React frontend can render the list without doing any data normalization.
    """

    id: str = Field(..., description="Airtable record id, e.g. 'recXXXX'")
    transaction_name: str
    address: Optional[str] = None
    client_email: Optional[str] = None
    cadastral_reference: Optional[str] = None
    type: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    landsize_m2: Optional[int] = None
    created_at: Optional[str] = Field(
        None, description="ISO date or whatever Airtable's `Create Date` column returned."
    )
    price: Optional[int] = Field(None, description="Airtable `Price` in EUR.")
    final_reno_cost: Optional[int] = Field(None, description="Airtable `Final reno cost` in EUR.")
    final_furniture_cost: Optional[int] = Field(
        None, description="Airtable `Final furniture cost` in EUR."
    )
    technical_project_costs: Optional[int] = Field(
        None, description="Airtable `Technical project costs` in EUR."
    )
    home_appliances_cost: Optional[int] = Field(
        None, description="Airtable `Home appliances cost` in EUR."
    )
    cleaning_cost: Optional[int] = Field(None, description="Airtable `Cleaning cost` in EUR.")
    real_estate_agent_fee: Optional[int] = Field(
        None, description="Airtable `Real estate agent fee` in EUR."
    )
    land_registry_cost: Optional[int] = Field(
        None, description="Airtable `Land registry cost` in EUR."
    )
    prophero_fee: Optional[int] = Field(None, description="Airtable `PropHero fee` in EUR.")
    notary_cost: Optional[int] = Field(None, description="Airtable `Notary cost` in EUR.")
    insurance: Optional[int] = Field(None, description="Airtable `Insurance` in EUR.")
    council_rate: Optional[int] = Field(None, description="Airtable `Council rate` in EUR.")
    service_charges: Optional[int] = Field(
        None, description="Airtable `Service charges` in EUR."
    )
    final_total_price: Optional[int] = Field(
        None,
        description=(
            "Airtable `Final total price` in EUR. This is the acquisition basis "
            "used as the amount the client paid."
        ),
    )
    real_settlement_date: Optional[str] = Field(
        None,
        description=(
            "Airtable `Real settlement date`. Used as the acquisition anchor "
            "for the market-appreciation lookup."
        ),
    )
    town_record_id: Optional[str] = Field(
        None,
        description=(
            "Airtable record id for the linked Town (from Properties). When "
            "present, the price-series layer resolves the municipality "
            "directly instead of falling back to the geocoder's name match."
        ),
    )


class TransactionDetail(TransactionSummary):
    """Full transaction record for the detail view. Includes the raw Airtable
    fields blob so the UI can show additional context not yet promoted to
    typed fields (we promote as we add columns to the search UI).
    """

    raw_fields: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Verbatim Airtable `fields` blob for the record. Lookup columns "
            "are kept as arrays here — only the typed shortcuts above are flattened."
        ),
    )


class CoachTransactionValuationResponse(BaseModel):
    """Result of turning an Airtable transaction into a valuation."""

    transaction: TransactionDetail
    valuation_request: ValuationRequest
    valuation: ValuationResponse


class CoachEmailSendRequest(BaseModel):
    """Editable email payload submitted from the coach UI."""

    to: str = Field(..., min_length=3, max_length=200)
    subject: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=10000)


class CoachEmailSendResponse(BaseModel):
    sent: bool
    message: str


class SimpleValuationResponse(BaseModel):
    """
    Slim contract designed for external integrations (Apps Script, Sheets, Zapier, etc.).
    Stable on purpose: do not break existing callers when the internal /api/valuation
    response shape evolves.
    """

    address: str
    price: Optional[int] = Field(
        None, description="Estimated sale price in EUR (currently from Idealista listings)"
    )
    asking_price: Optional[int] = Field(
        None, description="Average asking price of recent comparables in EUR"
    )
    closing_price: Optional[int] = Field(
        None, description="Average closing price of recent comparables in EUR"
    )
    negotiation_factor: Optional[float] = Field(
        None,
        description=(
            "(asking - closing) / asking, expressed as a decimal (e.g. 0.063 = 6.3%). "
            "Higher means buyers are negotiating bigger discounts off asking."
        ),
    )
    comparables_used: int = Field(
        0, description="Number of Idealista listings used to compute `price`"
    )
    is_mock: bool = Field(
        False,
        description=(
            "True when asking_price / closing_price / negotiation_factor come from "
            "the mocked market-transactions layer (Phase 2 will replace with real data)."
        ),
    )


# LeadResponse / ValuationStatusResponse hold forward references to
# ValuationResponse — resolve them now that all models in this file are
# defined. Pydantic v2 requires this when the referenced model lives below the
# referer in source order.
LeadResponse.model_rebuild()
ValuationStatusResponse.model_rebuild()
ReportPdfRenderRequest.model_rebuild()
