from pydantic import BaseModel, Field
from typing import Optional


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


class LeadResponse(BaseModel):
    """Acknowledgement returned to the frontend immediately. The email send
    happens in a BackgroundTask so the UX doesn't block on 5-15s of network."""

    lead_id: int
    valuation_id: int
    valuation: "ValuationResponse"
    email_scheduled: bool = Field(
        ...,
        description="True when an email send was queued. False when RESEND_API_KEY is unset (dev mode).",
    )


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
    dataset: Optional[ComparablesDataset] = None
    regression: Optional[RegressionResult] = None


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


# LeadResponse holds a forward reference to ValuationResponse — resolve it now
# that all models in this file are defined. Pydantic v2 requires this when the
# referenced model lives below the referer in source order.
LeadResponse.model_rebuild()
