import type {
  LeadInfo,
  LeadResponse,
  ResolvedAddress,
  ValuationRequest,
  ValuationResponse,
} from './types'

export const API_BASE =
  import.meta.env.VITE_API_URL ?? 'http://localhost:8001'

const SHARED_HEADERS = {
  'Content-Type': 'application/json',
  // Skips the ngrok-free.app browser warning interstitial so fetch returns JSON, not HTML.
  'ngrok-skip-browser-warning': 'true',
} as const

const FETCH_HEADERS: HeadersInit = {
  'ngrok-skip-browser-warning': 'true',
}

// Backend pipeline normally finishes in 40-70s but CAPTCHAs can push it further.
// 120s is the hard ceiling — past this we surface a timeout instead of hanging forever.
const VALUATION_TIMEOUT_MS = 120_000

export type ValuationErrorCode = 'timeout' | 'network' | 'server'

export class ValuationError extends Error {
  code: ValuationErrorCode
  status?: number

  constructor(code: ValuationErrorCode, message: string, status?: number) {
    super(message)
    this.name = 'ValuationError'
    this.code = code
    this.status = status
  }
}

/**
 * POST helper used by the slow endpoints (`/api/valuation`, `/api/lead`).
 * Wraps the fetch in an AbortController so we can enforce a hard timeout, and
 * normalizes errors into `ValuationError` so the UI can distinguish between
 * timeout / network / server-side failures and react accordingly.
 */
async function postJsonWithTimeout<T>(
  path: string,
  payload: unknown,
  timeoutMs: number,
): Promise<T> {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs)

  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: SHARED_HEADERS,
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
  } catch (err) {
    if ((err as { name?: string })?.name === 'AbortError') {
      throw new ValuationError('timeout', `Request timed out after ${timeoutMs}ms`)
    }
    throw new ValuationError('network', `Network error: ${(err as Error).message ?? 'unknown'}`)
  } finally {
    window.clearTimeout(timeoutId)
  }

  if (!res.ok) {
    // Try to surface FastAPI-style {"detail": "..."} bodies so the user sees
    // something more useful than just the HTTP code.
    let detail = ''
    try {
      const body = (await res.json()) as { detail?: string }
      if (body?.detail) detail = `: ${body.detail}`
    } catch {
      /* non-JSON body — ignore */
    }
    throw new ValuationError('server', `API error ${res.status}${detail}`, res.status)
  }

  return res.json() as Promise<T>
}

export async function valuateProperty(request: ValuationRequest): Promise<ValuationResponse> {
  return postJsonWithTimeout<ValuationResponse>('/api/valuation', request, VALUATION_TIMEOUT_MS)
}

/**
 * Submit lead + valuation in one request. The backend persists the lead in
 * SQLite, runs the valuation, and schedules the PDF + email send as a
 * BackgroundTask, so this returns as soon as the valuation is ready (~5-15s
 * for the valuation, +3-5s extra in background for email delivery).
 */
export function submitLead(payload: {
  lead: LeadInfo
  valuation_request: ValuationRequest
}): Promise<LeadResponse> {
  return postJsonWithTimeout<LeadResponse>('/api/lead', payload, VALUATION_TIMEOUT_MS)
}

/**
 * Render the valuation PDF and trigger a browser download. Useful for the
 * "Descargar PDF" button on the results page — the user already received the
 * report by email but may want to re-download it without checking their inbox.
 */
export async function downloadReportPdf(request: ValuationRequest): Promise<void> {
  const res = await fetch(`${API_BASE}/api/report/pdf`, {
    method: 'POST',
    headers: SHARED_HEADERS,
    body: JSON.stringify(request),
  })
  if (!res.ok) {
    throw new ValuationError('server', `PDF download failed: ${res.status}`, res.status)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `prophero-valoracion-${new Date().toISOString().slice(0, 10)}.pdf`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export async function autocompleteAddresses(
  query: string,
  { limit = 5, signal }: { limit?: number; signal?: AbortSignal } = {},
): Promise<ResolvedAddress[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) })
  const res = await fetch(`${API_BASE}/api/addresses/autocomplete?${params}`, {
    headers: FETCH_HEADERS,
    signal,
  })

  if (!res.ok) {
    throw new Error(`Autocomplete error: ${res.status}`)
  }

  return res.json() as Promise<ResolvedAddress[]>
}
