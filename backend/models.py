from pydantic import BaseModel, Field
from typing import Optional


class ValuationRequest(BaseModel):
    address: str = Field(..., description="Full address of the property")
    m2: int = Field(..., gt=0, description="Surface area in square meters")
    bedrooms: int = Field(..., ge=0, description="Number of bedrooms")
    bathrooms: int = Field(..., ge=1, description="Number of bathrooms")


class MunicipioInfo(BaseModel):
    name: str
    slug: str
    province: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


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


class ValuationStats(BaseModel):
    total_comparables: int
    avg_price: Optional[int] = None
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    avg_price_per_m2: Optional[int] = None
    estimated_value: Optional[int] = None
    price_range_low: Optional[int] = None
    price_range_high: Optional[int] = None


class ValuationResponse(BaseModel):
    municipio: MunicipioInfo
    listings: list[Listing]
    stats: ValuationStats
    search_url: str
