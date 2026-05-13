import type { ResolvedAddress, ValuationRequest, ValuationResponse } from './types'

export const API_BASE =
  import.meta.env.VITE_API_URL ?? 'https://3b41-195-158-89-154.ngrok-free.app'

const DEFAULT_HEADERS: HeadersInit = {
  // Skips the ngrok-free.app browser warning interstitial so fetch returns JSON, not HTML.
  'ngrok-skip-browser-warning': 'true',
}

export async function valuateProperty(request: ValuationRequest): Promise<ValuationResponse> {
  const res = await fetch(`${API_BASE}/api/valuation`, {
    method: 'POST',
    headers: {
      ...DEFAULT_HEADERS,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  })

  if (!res.ok) {
    throw new Error(`API error: ${res.status}`)
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
