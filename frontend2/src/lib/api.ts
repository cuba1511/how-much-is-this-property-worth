import type { ValuationRequest, ValuationResponse } from './types'

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8001'

export async function valuateProperty(request: ValuationRequest): Promise<ValuationResponse> {
  const res = await fetch(`${API_BASE}/api/valuation`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })

  if (!res.ok) {
    throw new Error(`API error: ${res.status}`)
  }

  return res.json() as Promise<ValuationResponse>
}
