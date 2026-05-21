import type {
  CadastralReferenceLookupResponse,
  CadastralUnitsResponse,
  LeadInfo,
  LeadResponse,
  ResolvedAddress,
  ValuationRequest,
  ValuationResponse,
  ValuationStatusResponse,
} from './types'

// Dev: localhost API. Production VPS: empty → same-origin /api via Caddy.
// Vercel/Railway: set VITE_API_URL at build time in the host dashboard.
export const API_BASE =
  import.meta.env.VITE_API_URL ??
  (import.meta.env.DEV ? 'http://localhost:8001' : '')

const SHARED_HEADERS = {
  'Content-Type': 'application/json',
  // Skips the ngrok-free.app browser warning interstitial so fetch returns JSON, not HTML.
  'ngrok-skip-browser-warning': 'true',
} as const

const FETCH_HEADERS: HeadersInit = {
  'ngrok-skip-browser-warning': 'true',
}

// Backend caps the synchronous portion of /api/lead at 75s (see
// `LEAD_SYNC_VALUATION_TIMEOUT_S` in backend/main.py). 90s on the client
// gives the backend headroom to respond with the 'pending' fallback before
// the browser aborts; this is what keeps the analyzing modal from ever
// hanging forever — even slow Bright Data sessions resolve to either
// 'ready' or 'pending', never to a client-side AbortError.
const VALUATION_TIMEOUT_MS = 90_000

export type ValuationErrorCode = 'timeout' | 'network' | 'server'

export class ValuationError extends Error {
  code: ValuationErrorCode
  status?: number
  /** Server-supplied detail (e.g. FastAPI's `detail` field). When present
   *  the UI can show this verbatim instead of a generic translated string. */
  detail?: string

  constructor(code: ValuationErrorCode, message: string, status?: number, detail?: string) {
    super(message)
    this.name = 'ValuationError'
    this.code = code
    this.status = status
    this.detail = detail
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
    let detail: string | undefined
    try {
      const body = (await res.json()) as { detail?: string }
      if (body?.detail) detail = body.detail
    } catch {
      /* non-JSON body — ignore */
    }
    throw new ValuationError(
      'server',
      detail ? `API error ${res.status}: ${detail}` : `API error ${res.status}`,
      res.status,
      detail,
    )
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
 * Fetch the current state of a persisted valuation. Used by the frontend
 * after `/api/lead` returns `status: 'pending'` to keep polling until the
 * background retry finishes, so the user lands on the results dashboard
 * instead of dead-ending on the "we'll email you" screen.
 *
 * Returns a typed shape (no throwing on 'pending' / 'failed'); callers
 * inspect `status` to decide whether to keep polling, render results, or
 * give up.
 */
export async function getValuationStatus(
  valuationId: number,
  signal?: AbortSignal,
): Promise<ValuationStatusResponse> {
  const res = await fetch(
    `${API_BASE}/api/valuations/${valuationId}/status`,
    { headers: FETCH_HEADERS, signal },
  )

  if (!res.ok) {
    let detail: string | undefined
    try {
      const body = (await res.json()) as { detail?: string }
      if (body?.detail) detail = body.detail
    } catch {
      /* ignore */
    }
    throw new ValuationError(
      'server',
      detail ?? `Status check failed: ${res.status}`,
      res.status,
      detail,
    )
  }

  return res.json() as Promise<ValuationStatusResponse>
}

export interface PollValuationOptions {
  /** Milliseconds between polls. Defaults to 3000. */
  intervalMs?: number
  /** Hard ceiling on total polling time. Past this we give up and let the
   *  caller fall back to the "we'll email you" screen. Defaults to 20 min
   *  so slow real-world valuations (Idealista CAPTCHAs, Bright Data warm-
   *  up, Catastro residential proxy round-trips) actually reach the
   *  report instead of dead-ending at the email fallback. The earlier
   *  4-min ceiling was tripping on every slow valuation in prod. */
  maxTotalMs?: number
  /** Optional abort signal — wired to the in-flight fetch so the caller can
   *  cancel the polling loop (e.g. user navigated away). */
  signal?: AbortSignal
}

export type PollOutcome =
  | { kind: 'ready'; valuation: ValuationResponse }
  | { kind: 'failed'; error?: string }
  | { kind: 'timeout' }
  | { kind: 'aborted' }

/**
 * Poll `getValuationStatus` until the valuation is ready, fails, or we hit
 * the `maxTotalMs` ceiling. Each individual fetch error (network blips) is
 * swallowed so transient failures don't kill the polling loop — only the
 * final outcome matters.
 */
export async function pollValuationUntilReady(
  valuationId: number,
  {
    intervalMs = 3_000,
    maxTotalMs = 20 * 60_000,
    signal,
  }: PollValuationOptions = {},
): Promise<PollOutcome> {
  const start = Date.now()

  while (true) {
    if (signal?.aborted) return { kind: 'aborted' }
    if (Date.now() - start > maxTotalMs) return { kind: 'timeout' }

    try {
      const status = await getValuationStatus(valuationId, signal)
      if (status.status === 'ready' && status.valuation) {
        return { kind: 'ready', valuation: status.valuation }
      }
      if (status.status === 'failed') {
        return { kind: 'failed', error: status.error ?? undefined }
      }
      // 'pending' → fall through to sleep + retry.
    } catch (err) {
      if ((err as { name?: string })?.name === 'AbortError') {
        return { kind: 'aborted' }
      }
      // Swallow transient errors and keep polling — only the ceiling matters.
    }

    await new Promise<void>((resolve) => {
      const id = window.setTimeout(resolve, intervalMs)
      signal?.addEventListener(
        'abort',
        () => {
          window.clearTimeout(id)
          resolve()
        },
        { once: true },
      )
    })
  }
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

/** Hard ceiling on the Catastro-by-address lookup. The backend itself caps the
 *  upstream call at 15s but a slow EC2 → Catastro hop, plus our own TLS/DNS,
 *  can push past that. A frontend timeout guarantees the user always sees an
 *  outcome (success / error) instead of an indefinite spinner. */
const CATASTRO_LOOKUP_TIMEOUT_MS = 20_000

/** Thrown by `lookupCadastralUnits` when our own client-side timer fires.
 *  Distinct from `AbortError` (which signals an upstream / caller-driven
 *  cancellation) so the UI can keep ignoring AbortError but still surface
 *  timeouts as a real error state. */
export class CatastroLookupTimeoutError extends Error {
  constructor() {
    super('Catastro lookup timed out')
    this.name = 'CatastroLookupTimeoutError'
  }
}

export async function lookupCadastralUnits(
  address: ResolvedAddress,
  signal?: AbortSignal,
): Promise<CadastralUnitsResponse> {
  const controller = new AbortController()
  // Chain the caller's signal: if either fires, we abort.
  const onUpstreamAbort = () => controller.abort()
  if (signal) {
    if (signal.aborted) controller.abort()
    else signal.addEventListener('abort', onUpstreamAbort, { once: true })
  }
  let timedOut = false
  const timeoutId = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, CATASTRO_LOOKUP_TIMEOUT_MS)

  try {
    const res = await fetch(`${API_BASE}/api/catastro/units/lookup`, {
      method: 'POST',
      headers: SHARED_HEADERS,
      body: JSON.stringify(address),
      signal: controller.signal,
    })

    if (!res.ok) {
      let detail = ''
      try {
        const body = (await res.json()) as { detail?: string }
        if (body?.detail) detail = `: ${body.detail}`
      } catch {
        /* ignore */
      }
      throw new Error(`Catastro lookup error ${res.status}${detail}`)
    }

    return (await res.json()) as CadastralUnitsResponse
  } catch (err) {
    // Rewrite timer-driven aborts so the caller can distinguish them from
    // genuine user cancellations.
    if (
      timedOut &&
      err instanceof Error &&
      (err.name === 'AbortError' || err.name === 'TimeoutError')
    ) {
      throw new CatastroLookupTimeoutError()
    }
    throw err
  } finally {
    clearTimeout(timeoutId)
    if (signal) signal.removeEventListener('abort', onUpstreamAbort)
  }
}

/**
 * Resolve a property directly from its cadastral reference (14 or 20 chars).
 * Returns the matching unit(s) plus a geocoded `ResolvedAddress` ready to
 * feed into the valuation pipeline (skips the address-autocomplete step).
 */
export async function lookupByCadastralReference(
  reference: string,
  signal?: AbortSignal,
): Promise<CadastralReferenceLookupResponse> {
  const res = await fetch(`${API_BASE}/api/catastro/by-reference`, {
    method: 'POST',
    headers: SHARED_HEADERS,
    body: JSON.stringify({ reference }),
    signal,
  })

  if (!res.ok) {
    let detail: string | undefined
    try {
      const body = (await res.json()) as { detail?: string }
      if (body?.detail) detail = body.detail
    } catch {
      /* ignore */
    }
    throw new ValuationError(
      'server',
      detail ?? `Catastro lookup error ${res.status}`,
      res.status,
      detail,
    )
  }

  return res.json() as Promise<CadastralReferenceLookupResponse>
}
