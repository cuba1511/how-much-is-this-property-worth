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
  real_settlement_date: string | null
  town_record_id: string | null
}

export interface TransactionDetail extends TransactionSummary {
  raw_fields: Record<string, unknown>
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
  { limit = 25, signal }: { limit?: number; signal?: AbortSignal } = {},
): Promise<TransactionSummary[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) })
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
  return handleResponse<TransactionSummary[]>(res)
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
  { live = true }: { live?: boolean } = {},
): Promise<CoachTransactionValuationResponse> {
  const params = new URLSearchParams({ live: String(live) })
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

export async function sendTransactionEmail(
  recordId: string,
  payload: { to: string; subject: string; body: string },
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
