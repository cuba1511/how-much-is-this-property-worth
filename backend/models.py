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
