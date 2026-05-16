import type { LeadInfo, LeadResponse, ValuationRequest, ValuationResponse } from './types'

const API_BASE = import.meta.env.VITE_API_URL ?? 'https://5911-195-158-89-154.ngrok-free.app'

const SHARED_HEADERS = {
  'Content-Type': 'application/json',
  // Skips the ngrok-free.app browser warning interstitial so fetch returns JSON, not HTML.
  'ngrok-skip-browser-warning': 'true',
} as const

async function postJson<T>(path: string, payload: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: SHARED_HEADERS,
    body: JSON.stringify(payload),
  })

  if (!res.ok) {
    // Try to surface FastAPI-style {"detail": "..."} bodies when present so the
    // user sees something more useful than just the HTTP code.
    let detail = ''
    try {
      const body = (await res.json()) as { detail?: string }
      if (body?.detail) detail = `: ${body.detail}`
    } catch {
      /* non-JSON body — ignore */
    }
    throw new Error(`API error ${res.status}${detail}`)
  }

  return res.json() as Promise<T>
}

/** Quick valuation without persisting a lead — used for the "explore" flow. */
export function valuateProperty(request: ValuationRequest): Promise<ValuationResponse> {
  return postJson<ValuationResponse>('/api/valuation', request)
}

/**
 * Submit lead + valuation in one request. The backend persists the lead in
 * SQLite, runs the valuation, and schedules the PDF + email send as a
 * BackgroundTask, so this returns as soon as the valuation is ready (~5-15s)
 * without blocking on email delivery (~3-5s extra).
 */
export function submitLead(payload: {
  lead: LeadInfo
  valuation_request: ValuationRequest
}): Promise<LeadResponse> {
  return postJson<LeadResponse>('/api/lead', payload)
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
    throw new Error(`PDF download failed: ${res.status}`)
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
