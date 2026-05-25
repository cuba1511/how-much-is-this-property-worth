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

export type LeadValuationStatus = 'ready' | 'pending' | 'failed'

export interface LeadResponse {
  lead_id: number
  valuation_id: number
  /**
   * Null when `status !== 'ready'` — backend is finishing the valuation
   * asynchronously and the user will receive the report by email.
   */
  valuation: ValuationResponse | null
  status: LeadValuationStatus
  email_scheduled: boolean
  message?: string | null
}

/** GET /api/valuations/{id}/status — used by the frontend to poll a valuation
 *  whose `/api/lead` returned `status='pending'`, so it can transition to the
 *  results dashboard the moment the background retry completes. */
export interface ValuationStatusResponse {
  valuation_id: number
  status: LeadValuationStatus
  valuation: ValuationResponse | null
  error?: string | null
}

export interface CadastralReferenceLookupResponse {
  reference: string
  is_parcel: boolean
  units: CadastralUnit[]
  resolved_address: ResolvedAddress | null
  catastro_address_label?: string | null
}

/** Which input shape the user chose to identify the property: a street address
 *  (Photon/Nominatim → Catastro lookup by portal) or a cadastral reference
 *  (Catastro DNPRC → reverse geocode to a `ResolvedAddress`). Lives in types
 *  because both the Hero and the in-form Step use it and it must survive the
 *  hand-off between them. */
export type IdentificationMode = 'address' | 'reference'

/** Snapshot of what the user resolved in the Hero before opening the form.
 *  When `mode === 'address'` only `address` is populated and the form will
 *  query Catastro for units on step 0. When `mode === 'reference'` the
 *  Hero already called `/api/catastro/by-reference`, so units (and possibly
 *  the unique selected unit) are pre-populated and the form should NOT
 *  refetch — it just hydrates step 0. */
export interface IdentificationStartPayload {
  mode: IdentificationMode
  address: ResolvedAddress | null
  units?: CadastralUnit[]
  selectedUnit?: CadastralUnit | null
  isParcel?: boolean
  referenceLabel?: string | null
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
  rent_timeline?: string | null
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

/** Real-data zone appreciation between the property's settlement date and the
 *  most recent monthly observation in the TF Labs municipal price series. */
export interface MarketAppreciation {
  town_id: string | null
  town_name: string
  ine_code: string | null
  settlement_date: string
  from_period: string
  from_eur_per_m2: number
  to_period: string
  to_eur_per_m2: number
  pct_change: number
  annualized_pct_change: number | null
  months_elapsed: number
  sample_quality: 'exact' | 'nearest_available'
  resolution_strategy: 'airtable_town_id' | 'ine_code' | 'name_match'
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
  market_appreciation?: MarketAppreciation | null
}
