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


class ValuationRequest(BaseModel):
    address: str = Field(..., description="Full address of the property")
    m2: int = Field(..., gt=0, description="Surface area in square meters")
    bedrooms: int = Field(..., ge=0, description="Number of bedrooms")
    bathrooms: int = Field(..., ge=1, description="Number of bathrooms")
    selected_address: Optional[ResolvedAddress] = None


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
    source_stage: Optional[str] = None


class ValuationStats(BaseModel):
    total_comparables: int
    avg_price: Optional[int] = None
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    avg_price_per_m2: Optional[int] = None
    estimated_value: Optional[int] = None
    price_range_low: Optional[int] = None
    price_range_high: Optional[int] = None


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
