export interface CadastralUnit {
  cadastral_reference: string
  block?: string | null
  staircase?: string | null
  floor?: string | null
  door?: string | null
  built_area_m2?: number | null
  label: string
}

export interface CadastralUnitsResponse {
  units: CadastralUnit[]
  query: Record<string, string>
}

export interface ResolvedAddress {
  label: string
  lat: number
  lon: number
  municipality: string
  province?: string | null
  road?: string | null
  house_number?: string | null
  postcode?: string | null
  neighbourhood?: string | null
  quarter?: string | null
  city_district?: string | null
  country?: string | null
  provider: string
  provider_id?: string | null
  precision?: string | null
}

export interface LeadInfo {
  full_name: string
  email: string
  phone: string
}

export interface LeadResponse {
  lead_id: number
  valuation_id: number
  valuation: ValuationResponse
  email_scheduled: boolean
}

export interface PropertyFeatures {
  pool: boolean
  terrace: boolean
  elevator: boolean
  parking: boolean
}

export interface ValuationRequest {
  address: string
  m2: number
  bedrooms: number
  bathrooms: number
  property_type?: string | null
  property_condition?: string | null
  features?: PropertyFeatures | null
  valuation_intent?: string | null
  sell_reason?: string | null
  sell_timeline?: string | null
  selected_address?: ResolvedAddress | null
  selected_cadastral_unit?: CadastralUnit | null
  lead?: LeadInfo
}

export interface MunicipioInfo {
  name: string
  slug: string
  province?: string | null
  lat?: number | null
  lon?: number | null
  road?: string | null
  neighbourhood?: string | null
  quarter?: string | null
  city_district?: string | null
  postcode?: string | null
}

export interface Listing {
  title: string
  price?: number | null
  m2?: number | null
  price_per_m2?: number | null
  bedrooms?: number | null
  bathrooms?: number | null
  address?: string | null
  url: string
  image_url?: string | null
  floor?: string | null
  source_stage?: string | null
}

export interface ValuationStats {
  total_comparables: number
  avg_price?: number | null
  min_price?: number | null
  max_price?: number | null
  avg_price_per_m2?: number | null
  estimated_value?: number | null
  price_range_low?: number | null
  price_range_high?: number | null
  estimation_method?: 'ols_lstsq' | 'avg_ppm2' | null
  confidence_method?: 'sample_std' | 'flat_pct' | null
}

export interface MarketTransactionChartPoint {
  label: string
  asking_price?: number | null
  closing_price?: number | null
  negotiation_margin_pct?: number | null
}

export interface MarketTransaction {
  id: string
  address?: string | null
  m2?: number | null
  bedrooms?: number | null
  bathrooms?: number | null
  asking_price?: number | null
  closing_price?: number | null
  asking_price_per_m2?: number | null
  closing_price_per_m2?: number | null
  negotiation_margin_pct?: number | null
  close_date?: string | null
  days_on_market?: number | null
  source: string
  distance_m?: number | null
}

export interface MarketTransactionsSummary {
  total_transactions: number
  avg_asking_price?: number | null
  avg_closing_price?: number | null
  avg_asking_price_per_m2?: number | null
  avg_closing_price_per_m2?: number | null
  asking_vs_closing_gap_pct?: number | null
  negotiation_margin_pct?: number | null
  sample_size: number
  chart_series: MarketTransactionChartPoint[]
}

export interface MarketTransactions {
  summary: MarketTransactionsSummary
  transactions: MarketTransaction[]
}

export interface SearchStageResult {
  name: string
  label: string
  query: string
  search_url: string
  listings_found: number
  duration_ms: number
  area_min?: number | null
  area_max?: number | null
  bedrooms_mode: string
  bathrooms_mode: string
}

export interface SearchMetadata {
  strategy: string
  target_comparables: number
  final_stage: string
  total_duration_ms: number
  stages: SearchStageResult[]
}

export interface ValuationResponse {
  municipio: MunicipioInfo
  listings: Listing[]
  stats: ValuationStats
  search_url: string
  search_metadata: SearchMetadata
  market_transactions?: MarketTransactions | null
}
