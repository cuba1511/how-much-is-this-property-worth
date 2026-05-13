import type { ValuationRequest, ValuationResponse } from './types'

const API_BASE = import.meta.env.VITE_API_URL ?? 'https://5911-195-158-89-154.ngrok-free.app'

export async function valuateProperty(request: ValuationRequest): Promise<ValuationResponse> {
  const res = await fetch(`${API_BASE}/api/valuation`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      // Skips the ngrok-free.app browser warning interstitial so fetch returns JSON, not HTML.
      'ngrok-skip-browser-warning': 'true',
    },
    body: JSON.stringify(request),
  })

  if (!res.ok) {
    throw new Error(`API error: ${res.status}`)
  }

  return res.json() as Promise<ValuationResponse>
}
