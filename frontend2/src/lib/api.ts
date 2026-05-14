import type { ResolvedAddress, ValuationRequest, ValuationResponse } from './types'

export const API_BASE =
  import.meta.env.VITE_API_URL ?? 'https://3b41-195-158-89-154.ngrok-free.app'

const DEFAULT_HEADERS: HeadersInit = {
  // Skips the ngrok-free.app browser warning interstitial so fetch returns JSON, not HTML.
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

export async function valuateProperty(request: ValuationRequest): Promise<ValuationResponse> {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), VALUATION_TIMEOUT_MS)

  let res: Response
  try {
    res = await fetch(`${API_BASE}/api/valuation`, {
      method: 'POST',
      headers: {
        ...DEFAULT_HEADERS,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
      signal: controller.signal,
    })
  } catch (err) {
    if ((err as { name?: string })?.name === 'AbortError') {
      throw new ValuationError('timeout', `Valuation timed out after ${VALUATION_TIMEOUT_MS}ms`)
    }
    throw new ValuationError('network', `Network error: ${(err as Error).message ?? 'unknown'}`)
  } finally {
    window.clearTimeout(timeoutId)
  }

  if (!res.ok) {
    throw new ValuationError('server', `API error: ${res.status}`, res.status)
  }

  return res.json() as Promise<ValuationResponse>
}

export async function autocompleteAddresses(
  query: string,
  { limit = 5, signal }: { limit?: number; signal?: AbortSignal } = {},
): Promise<ResolvedAddress[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) })
  const res = await fetch(`${API_BASE}/api/addresses/autocomplete?${params}`, {
    headers: DEFAULT_HEADERS,
    signal,
  })

  if (!res.ok) {
    throw new Error(`Autocomplete error: ${res.status}`)
  }

  return res.json() as Promise<ResolvedAddress[]>
}
