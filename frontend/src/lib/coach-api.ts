/**
 * Client for `/api/coach/*` — the Airtable-backed transactions interface.
 *
 * The PAT lives on the backend; this client just attaches the
 * `X-Coach-Password` header that the FastAPI dependency checks against the
 * `COACH_ACCESS_PASSWORD` env var. The password is persisted in
 * localStorage so the coach UI doesn't ask for it on every page load.
 */

import { API_BASE } from './api'
import type { ValuationRequest, ValuationResponse } from './types'

const COACH_PASSWORD_STORAGE_KEY = 'prophero.coach.password'
const COACH_REQUEST_TIMEOUT_MS = 20_000

export interface TransactionSummary {
  id: string
  transaction_name: string
  address: string | null
  client_email: string | null
  cadastral_reference: string | null
  type: string | null
  bedrooms: number | null
  bathrooms: number | null
  landsize_m2: number | null
  created_at: string | null
  price: number | null
  final_reno_cost: number | null
  final_furniture_cost: number | null
  technical_project_costs: number | null
  home_appliances_cost: number | null
  cleaning_cost: number | null
  real_estate_agent_fee: number | null
  land_registry_cost: number | null
  prophero_fee: number | null
  notary_cost: number | null
  insurance: number | null
  council_rate: number | null
  service_charges: number | null
  final_total_price: number | null
  purchase_eur_per_m2: number | null
  real_settlement_date: string | null
  town_record_id: string | null
  coach_id: string | null
  coach_name: string | null
  coach_email: string | null
  account_manager_id: string | null
  account_manager_name: string | null
  appreciation_pct: number | null
  appreciation_from_period: string | null
  appreciation_to_period: string | null
  appreciation_town_name: string | null
  estimated_current_value: number | null
  capital_gain: number | null
}

export interface TransactionDetail extends TransactionSummary {
  raw_fields: Record<string, unknown>
}

export interface TransactionSearchResponse {
  records: TransactionSummary[]
  next_offset: string | null
  page_size: number
  has_more: boolean
}

export interface CoachTransactionValuationResponse {
  transaction: TransactionDetail
  valuation_request: ValuationRequest
  valuation: ValuationResponse
}

export interface CoachEmailSendResponse {
  sent: boolean
  message: string
}

export interface CoachAutoEmailPreviewResponse {
  transaction_id: string
  transaction: TransactionDetail
  valuation_request: ValuationRequest
  valuation: ValuationResponse
  client_email: string | null
  delivered_to: string | null
  subject: string
  body: string
  appreciation_pct: number | null
  capital_gain: number | null
  estimated_value: number | null
  review_warning: string | null
}

export interface CoachAutoEmailResponse {
  transaction_id: string
  sent: boolean
  skipped_reason: string | null
  delivered_to: string | null
  client_email: string | null
  subject: string
  appreciation_pct: number | null
  capital_gain: number | null
  estimated_value: number | null
}

export interface CoachEmailSendPayload {
  to: string
  subject: string
  body: string
  valuation_request?: ValuationRequest
  valuation?: ValuationResponse
  transaction?: TransactionDetail
  include_comparables?: boolean
}

export type CoachApiErrorCode = 'unauthorized' | 'not_found' | 'network' | 'server'

export class CoachApiError extends Error {
  code: CoachApiErrorCode
  status?: number
  detail?: string

  constructor(code: CoachApiErrorCode, message: string, status?: number, detail?: string) {
    super(message)
    this.name = 'CoachApiError'
    this.code = code
    this.status = status
    this.detail = detail
  }
}

function isAbortLikeError(err: unknown): boolean {
  if (!(err instanceof Error)) return false
  return err.name === 'AbortError' || err.message.toLowerCase().includes('aborted')
}

function asAbortError(): DOMException {
  return new DOMException('Request aborted', 'AbortError')
}

async function fetchWithTimeout(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const controller = new AbortController()
  const upstreamSignal = init.signal
  let timedOut = false

  const timeoutId = window.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, COACH_REQUEST_TIMEOUT_MS)

  const abortFromUpstream = () => controller.abort()
  if (upstreamSignal) {
    if (upstreamSignal.aborted) controller.abort()
    else upstreamSignal.addEventListener('abort', abortFromUpstream, { once: true })
  }

  try {
    return await fetch(input, { ...init, signal: controller.signal })
  } catch (err) {
    if (timedOut) {
      throw new CoachApiError(
        'network',
        `Network timeout after ${COACH_REQUEST_TIMEOUT_MS / 1000}s`,
      )
    }
    if (upstreamSignal?.aborted || isAbortLikeError(err)) throw asAbortError()
    throw err
  } finally {
    window.clearTimeout(timeoutId)
    upstreamSignal?.removeEventListener('abort', abortFromUpstream)
  }
}

export function getStoredCoachPassword(): string {
  if (typeof window === 'undefined') return ''
  try {
    return window.localStorage.getItem(COACH_PASSWORD_STORAGE_KEY) ?? ''
  } catch {
    return ''
  }
}

export function setStoredCoachPassword(value: string): void {
  if (typeof window === 'undefined') return
  try {
    if (value) {
      window.localStorage.setItem(COACH_PASSWORD_STORAGE_KEY, value)
    } else {
      window.localStorage.removeItem(COACH_PASSWORD_STORAGE_KEY)
    }
  } catch {
    /* ignore quota / privacy mode */
  }
}

export function clearStoredCoachPassword(): void {
  setStoredCoachPassword('')
}

function buildHeaders(): HeadersInit {
  const headers: Record<string, string> = {
    'ngrok-skip-browser-warning': 'true',
  }
  const pwd = getStoredCoachPassword()
  if (pwd) headers['X-Coach-Password'] = pwd
  return headers
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (res.ok) {
    return (await res.json()) as T
  }
  let detail: string | undefined
  try {
    const body = (await res.json()) as { detail?: string }
    if (body?.detail) detail = body.detail
  } catch {
    /* non-JSON body */
  }
  if (res.status === 401) {
    throw new CoachApiError('unauthorized', detail ?? 'Invalid coach password', 401, detail)
  }
  if (res.status === 404) {
    throw new CoachApiError('not_found', detail ?? 'Transaction not found', 404, detail)
  }
  throw new CoachApiError(
    'server',
    detail ? `API error ${res.status}: ${detail}` : `API error ${res.status}`,
    res.status,
    detail,
  )
}

export async function searchTransactions(
  query: string,
  {
    limit = 100,
    offset,
    signal,
  }: { limit?: number; offset?: string | null; signal?: AbortSignal } = {},
): Promise<TransactionSearchResponse> {
  const params = new URLSearchParams({ q: query, limit: String(limit) })
  if (offset) params.set('offset', offset)
  let res: Response
  try {
    res = await fetchWithTimeout(`${API_BASE}/api/coach/transactions?${params}`, {
      headers: buildHeaders(),
      signal,
    })
  } catch (err) {
    if (err instanceof CoachApiError) throw err
    if (isAbortLikeError(err)) throw asAbortError()
    throw new CoachApiError(
      'network',
      `Network error: ${(err as Error).message ?? 'unknown'}`,
    )
  }
  return handleResponse<TransactionSearchResponse>(res)
}

export async function getTransaction(
  recordId: string,
  { signal }: { signal?: AbortSignal } = {},
): Promise<TransactionDetail> {
  let res: Response
  try {
    res = await fetchWithTimeout(`${API_BASE}/api/coach/transactions/${encodeURIComponent(recordId)}`, {
      headers: buildHeaders(),
      signal,
    })
  } catch (err) {
    if (err instanceof CoachApiError) throw err
    if (isAbortLikeError(err)) throw asAbortError()
    throw new CoachApiError(
      'network',
      `Network error: ${(err as Error).message ?? 'unknown'}`,
    )
  }
  return handleResponse<TransactionDetail>(res)
}

export async function generateTransactionValuation(
  recordId: string,
  {
    live = true,
    includeComparables = true,
  }: { live?: boolean; includeComparables?: boolean } = {},
): Promise<CoachTransactionValuationResponse> {
  // ``include_comparables=false`` short-circuits the Idealista scrape on the
  // backend, so the request returns in <1s (the time it takes to geocode +
  // look up the TF Labs €/m² for the town). Useful when the coach only
  // needs the market anchor + Airtable context, not fresh comparables.
  const params = new URLSearchParams({
    live: String(live),
    include_comparables: String(includeComparables),
  })
  let res: Response
  try {
    res = await fetch(
      `${API_BASE}/api/coach/transactions/${encodeURIComponent(recordId)}/valuation?${params}`,
      {
        method: 'POST',
        headers: buildHeaders(),
      },
    )
  } catch (err) {
    throw new CoachApiError(
      'network',
      `Network error: ${(err as Error).message ?? 'unknown'}`,
    )
  }
  return handleResponse<CoachTransactionValuationResponse>(res)
}

/**
 * Trigger the no-scrape auto-pipeline: Airtable → TF Labs valuation → PDF →
 * branded email. Used by the bulk-send action on the coach worklist.
 *
 * Each call is self-contained and idempotent on the upstream side, so the
 * frontend safely fans this out in parallel (with a small concurrency cap so
 * we don't melt Airtable + Resend + Playwright at once).
 */
export async function sendTransactionAutoEmail(
  recordId: string,
  { signal }: { signal?: AbortSignal } = {},
): Promise<CoachAutoEmailResponse> {
  let res: Response
  try {
    res = await fetch(
      `${API_BASE}/api/coach/transactions/${encodeURIComponent(recordId)}/email/auto-send`,
      {
        method: 'POST',
        headers: buildHeaders(),
        signal,
      },
    )
  } catch (err) {
    if (isAbortLikeError(err)) throw asAbortError()
    throw new CoachApiError(
      'network',
      `Network error: ${(err as Error).message ?? 'unknown'}`,
    )
  }
  return handleResponse<CoachAutoEmailResponse>(res)
}

export async function previewTransactionAutoEmail(
  recordId: string,
  { signal }: { signal?: AbortSignal } = {},
): Promise<CoachAutoEmailPreviewResponse> {
  let res: Response
  try {
    res = await fetch(
      `${API_BASE}/api/coach/transactions/${encodeURIComponent(recordId)}/email/auto-preview`,
      {
        method: 'POST',
        headers: buildHeaders(),
        signal,
      },
    )
  } catch (err) {
    if (isAbortLikeError(err)) throw asAbortError()
    throw new CoachApiError(
      'network',
      `Network error: ${(err as Error).message ?? 'unknown'}`,
    )
  }
  return handleResponse<CoachAutoEmailPreviewResponse>(res)
}

export async function sendTransactionEmail(
  recordId: string,
  payload: CoachEmailSendPayload,
): Promise<CoachEmailSendResponse> {
  let res: Response
  try {
    res = await fetch(
      `${API_BASE}/api/coach/transactions/${encodeURIComponent(recordId)}/email/send`,
      {
        method: 'POST',
        headers: {
          ...buildHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      },
    )
  } catch (err) {
    throw new CoachApiError(
      'network',
      `Network error: ${(err as Error).message ?? 'unknown'}`,
    )
  }
  return handleResponse<CoachEmailSendResponse>(res)
}

/**
 * Probe whether the supplied password is valid without touching Airtable.
 * Returns true on 2xx, false on 401, throws on other errors so the UI can
 * distinguish "wrong password" from "API down".
 */
export async function probeCoachPassword(password: string): Promise<boolean> {
  let res: Response
  try {
    res = await fetchWithTimeout(`${API_BASE}/api/coach/auth/check`, {
      headers: {
        'ngrok-skip-browser-warning': 'true',
        'X-Coach-Password': password,
      },
    })
  } catch (err) {
    if (err instanceof CoachApiError) throw err
    throw new CoachApiError(
      'network',
      `Network error: ${(err as Error).message ?? 'unknown'}`,
    )
  }
  if (res.ok) return true
  if (res.status === 401) return false
  let detail: string | undefined
  try {
    const body = (await res.json()) as { detail?: string }
    if (body?.detail) detail = body.detail
  } catch {
    /* ignore */
  }
  throw new CoachApiError(
    'server',
    detail ? `API error ${res.status}: ${detail}` : `API error ${res.status}`,
    res.status,
    detail,
  )
}
