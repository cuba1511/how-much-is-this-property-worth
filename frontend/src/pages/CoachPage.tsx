import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'
import {
  AlertCircle,
  ArrowLeft,
  BarChart3,
  Building2,
  Calculator,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  Download,
  Eye,
  FileText,
  Filter,
  Loader2,
  LogOut,
  MailCheck,
  MapPin,
  Paperclip,
  Phone,
  Search,
  Send,
  Sparkles,
  TrendingUp,
  UserCircle2,
  X,
  type LucideIcon,
} from 'lucide-react'
import { Navbar } from '@/components/Navbar'
import { MapView } from '@/components/MapView'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  createReportPdfObjectUrl,
  downloadReportPdf,
  type ReportPdfPayload,
} from '@/lib/api'
import { stageRadiusMeters } from '@/lib/results'
import {
  CoachAutoEmailPreviewResponse,
  CoachTransactionValuationResponse,
  CoachApiError,
  TransactionDetail,
  TransactionSummary,
  clearStoredCoachPassword,
  generateTransactionValuation,
  getStoredCoachPassword,
  getTransaction,
  previewTransactionAutoEmail,
  probeCoachPassword,
  sendTransactionEmail,
  searchTransactions,
  setStoredCoachPassword,
} from '@/lib/coach-api'

const SEARCH_DEBOUNCE_MS = 300
const REPORT_PROGRESS_CAP = 0.95
const REPORT_PROGRESS_TAU_SECONDS = 30
const REPORT_LONG_RUNNING_HINT_AFTER_S = 90

type ReportLoadingPhaseKey =
  | 'resolving'
  | 'scraping'
  | 'enriching'
  | 'pricing'
  | 'reporting'

interface ReportLoadingPhase {
  key: ReportLoadingPhaseKey
  from: number
  icon: LucideIcon
  label: string
  detail: string
}

const REPORT_LOADING_PHASES: ReportLoadingPhase[] = [
  {
    key: 'resolving',
    from: 0,
    icon: MapPin,
    label: 'Resolviendo dirección',
    detail: 'Normalizamos la dirección de Airtable y ubicamos el municipio.',
  },
  {
    key: 'scraping',
    from: 4,
    icon: Search,
    label: 'Buscando comparables reales',
    detail: 'Abrimos Idealista en vivo y aplicamos filtros de zona, m², habitaciones y baños.',
  },
  {
    key: 'enriching',
    from: 20,
    icon: Building2,
    label: 'Leyendo anuncios activos',
    detail: 'Revisamos los mejores comparables para extraer precio, superficie y características útiles.',
  },
  {
    key: 'pricing',
    from: 40,
    icon: BarChart3,
    label: 'Calculando rango de salida',
    detail: 'Combinamos comparables, €/m² y regresión para construir el precio recomendado.',
  },
  {
    key: 'reporting',
    from: 55,
    icon: Calculator,
    label: 'Armando reporte inversor',
    detail: 'Añadimos rango conservador, plusvalía de zona y lectura de mercado para el coach.',
  },
]

function computeReportProgress(elapsed: number): number {
  return Math.min(REPORT_PROGRESS_CAP, 1 - Math.exp(-elapsed / REPORT_PROGRESS_TAU_SECONDS))
}

function pickReportLoadingPhase(elapsed: number): ReportLoadingPhase {
  const finalPhaseStart = REPORT_LOADING_PHASES[REPORT_LOADING_PHASES.length - 1].from
  if (elapsed >= finalPhaseStart + 25) {
    const rotation: ReportLoadingPhaseKey[] = ['scraping', 'enriching', 'pricing', 'reporting']
    const key = rotation[Math.floor((elapsed - finalPhaseStart) / 25) % rotation.length]
    return REPORT_LOADING_PHASES.find((phase) => phase.key === key) ?? REPORT_LOADING_PHASES[0]
  }

  let current = REPORT_LOADING_PHASES[0]
  for (const phase of REPORT_LOADING_PHASES) {
    if (elapsed >= phase.from) current = phase
  }
  return current
}

function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return new Intl.NumberFormat('es-ES', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(value)
}

// Round to a "clean" step so coach narratives don't expose calculator precision
// like "151.842 €". €1.000 reads as a deliberate estimate, not a hard number.
function roundToStep(value: number, step = 1000): number {
  if (!Number.isFinite(value)) return 0
  return Math.round(value / step) * step
}

function formatCurrencyRange(low: number | null, high: number | null): string {
  if (low === null || high === null) return '—'
  if (low === high) return formatCurrency(low)
  const lowNumber = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0 }).format(low)
  return `${lowNumber} – ${formatCurrency(high)}`
}

function formatEmailCurrencyRange(low: number | null, high: number | null): string {
  if (low === null || high === null) return '—'
  if (low === high) return formatCurrency(low)
  return `${formatCurrency(low)} y ${formatCurrency(high)}`
}

// Build a "soft" band around an anchor so each scenario reads as a range, not
// a punctual number. Spread is intentionally narrow (~3%) so the three
// scenario bands don't collapse into one another; rounding to €1k keeps the
// price feel coach-driven rather than calculator-driven.
function priceBand(
  anchor: number | null | undefined,
  spreadPct: number,
  step = 1000,
): { low: number | null; high: number | null } {
  if (anchor === null || anchor === undefined || !Number.isFinite(anchor)) {
    return { low: null, high: null }
  }
  const rawLow = anchor * (1 - spreadPct)
  const rawHigh = anchor * (1 + spreadPct)
  const low = Math.max(0, roundToStep(rawLow, step))
  const high = Math.max(low + step, roundToStep(rawHigh, step))
  return { low, high }
}

function formatPricePerM2(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return `${new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0 }).format(value)} €/m²`
}

function formatDate(value: string | null): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString('es-ES', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

function formatNumber(value: number | null, suffix = ''): string {
  if (value === null || value === undefined) return '—'
  return `${value}${suffix}`
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

function formatEmailPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1).replace('.', ',')}%`
}

function totalSpent(row: TransactionSummary): number | null {
  return row.final_total_price ?? null
}

function pricePerM2(total: number | null | undefined, m2: number | null | undefined): number | null {
  if (!total || !m2) return null
  return Math.round(total / m2)
}

function purchasePricePerM2(row: TransactionSummary): number | null {
  return row.purchase_eur_per_m2 ?? pricePerM2(totalSpent(row), row.landsize_m2)
}

function acquisitionCosts(row: TransactionSummary): Array<{ label: string; value: number | null }> {
  return [
    { label: 'Reforma final', value: row.final_reno_cost },
    { label: 'Mobiliario final', value: row.final_furniture_cost },
    { label: 'Proyecto técnico', value: row.technical_project_costs },
    { label: 'Electrodomésticos', value: row.home_appliances_cost },
    { label: 'Limpieza', value: row.cleaning_cost },
    { label: 'Agencia inmobiliaria', value: row.real_estate_agent_fee },
    { label: 'Registro', value: row.land_registry_cost },
    { label: 'Fee PropHero', value: row.prophero_fee },
    { label: 'Notaría', value: row.notary_cost },
    { label: 'Seguro', value: row.insurance },
    { label: 'IBI / council rate', value: row.council_rate },
    { label: 'Gastos de comunidad', value: row.service_charges },
  ]
}

function capitalGain(exitPrice: number | null | undefined, invested: number | null): number | null {
  if (exitPrice === null || exitPrice === undefined || invested === null) return null
  return exitPrice - invested
}

function roiPercent(gain: number | null, invested: number | null): number | null {
  if (gain === null || !invested) return null
  return (gain / invested) * 100
}

function formatPeriod(period: string | null | undefined): string {
  if (!period) return '—'
  // CSV periods are 'YYYY-MM'; render as 'MMM YYYY' in Spanish.
  const [year, month] = period.split('-')
  const monthIdx = Number(month) - 1
  if (!year || Number.isNaN(monthIdx)) return period
  const date = new Date(Number(year), monthIdx, 1)
  return date.toLocaleDateString('es-ES', { month: 'short', year: 'numeric' })
}

function searchStageLabel(stage: string): string {
  switch (stage) {
    case 'same_street':
      return 'misma calle'
    case 'same_microzone':
      return 'microzona'
    case 'same_local_area':
      return 'área local'
    case 'municipality':
      return 'municipio'
    case 'alicante_local_box':
      return 'cerca de la dirección'
    case 'alicante_municipality':
      return 'municipio'
    default:
      return stage.replaceAll('_', ' ')
  }
}

function clientName(transactionName: string): string {
  return transactionName.split(' - ')[0]?.trim() || transactionName
}

function clientFirstName(transactionName: string): string {
  const name = clientName(transactionName)
  return name.split(/\s+/)[0]?.trim() || name
}

function formatSubjectGain(value: number | null): string | null {
  if (value === null) return null
  const roundedDown = Math.max(0, Math.floor(value / 1000) * 1000)
  return roundedDown > 0 ? formatCurrency(roundedDown) : null
}

function coachEmailArea(
  transaction: TransactionDetail,
  valuationResult: CoachTransactionValuationResponse,
): string {
  const address = `${transaction.address ?? ''} ${valuationResult.valuation_request.address ?? ''}`.toLowerCase()
  if (address.includes('torrefiel')) return 'Torrefiel'

  const selected = valuationResult.valuation_request.selected_address
  return (
    selected?.neighbourhood ||
    selected?.quarter ||
    selected?.city_district ||
    selected?.municipality ||
    valuationResult.valuation.market_appreciation?.town_name ||
    valuationResult.valuation.municipio.name
  )
}

export default function CoachPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { transactionId } = useParams<{ transactionId?: string }>()

  const [authed, setAuthed] = useState<boolean>(() => Boolean(getStoredCoachPassword()))

  const handleAuthed = useCallback(() => setAuthed(true), [])

  const handleLogout = useCallback(() => {
    clearStoredCoachPassword()
    setAuthed(false)
    navigate('/coach')
  }, [navigate])

  return (
    <>
      <Navbar />
      <main className="flex-1 w-full">
        <section className="px-md md:px-xl pt-xl pb-3xl">
          <div className="mx-auto w-full max-w-6xl">
            <header className="mb-lg flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-primary">
                  {t('coach.eyebrow')}
                </p>
                <h1 className="mt-1 text-3xl font-semibold tracking-tight text-ink">
                  {t('coach.title')}
                </h1>
                <p className="mt-1 text-sm text-ink-secondary">
                  {t('coach.subtitle')}
                </p>
              </div>
              {authed && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={handleLogout}
                  className="self-start text-ink-secondary"
                >
                  <LogOut className="h-4 w-4" />
                  {t('coach.logout')}
                </Button>
              )}
            </header>

            {!authed && <CoachLogin onAuthed={handleAuthed} />}
            {authed && !transactionId && (
              <TransactionSearchPanel
                onSelect={(id) => navigate(`/coach/${id}`)}
                onUnauthorized={handleLogout}
              />
            )}
            {authed && transactionId && (
              <TransactionDetailPanel
                key={transactionId}
                transactionId={transactionId}
                onBack={() => navigate('/coach')}
                onUnauthorized={handleLogout}
              />
            )}
          </div>
        </section>
      </main>
    </>
  )
}

interface CoachLoginProps {
  onAuthed: () => void
}

function CoachLogin({ onAuthed }: CoachLoginProps) {
  const { t } = useTranslation()
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!password.trim() || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      const ok = await probeCoachPassword(password.trim())
      if (!ok) {
        setError(t('coach.login.invalidPassword'))
        return
      }
      setStoredCoachPassword(password.trim())
      onAuthed()
    } catch (err) {
      const message =
        err instanceof CoachApiError ? err.message : (err as Error).message
      setError(message || t('coach.login.unknownError'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Card className="p-lg md:p-xl">
      <form onSubmit={handleSubmit} className="flex flex-col gap-md">
        <div>
          <h2 className="text-xl font-semibold text-ink">{t('coach.login.title')}</h2>
          <p className="mt-1 text-sm text-ink-secondary">{t('coach.login.subtitle')}</p>
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor="coach-password" className="text-sm font-medium text-ink">
            {t('coach.login.passwordLabel')}
          </label>
          <Input
            id="coach-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            autoFocus
            disabled={submitting}
          />
        </div>

        {error && (
          <div
            role="alert"
            className="rounded-xl border border-destructive/30 bg-destructive/5 px-md py-sm text-sm text-destructive"
          >
            {error}
          </div>
        )}

        <Button type="submit" disabled={submitting || !password.trim()}>
          {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
          {submitting ? t('coach.login.checking') : t('coach.login.submit')}
        </Button>
      </form>
    </Card>
  )
}

interface TransactionSearchPanelProps {
  onSelect: (transactionId: string) => void
  onUnauthorized: () => void
}

// Sort modes for the coach worklist. Capital-gain / appreciation sorts surface
// the highest-leverage transactions first; the "oldest" default mirrors the
// historical worklist behavior so old habits keep working.
type SortMode =
  | 'created_asc'
  | 'created_desc'
  | 'gain_desc'
  | 'appreciation_desc'
  | 'value_desc'

const SORT_OPTIONS: Array<{ value: SortMode; label: string }> = [
  { value: 'gain_desc', label: 'Capital gain ↓' },
  { value: 'appreciation_desc', label: 'Revalorización ↓' },
  { value: 'value_desc', label: 'Valor estimado ↓' },
  { value: 'created_desc', label: 'Más recientes primero' },
  { value: 'created_asc', label: 'Más antiguas primero' },
]

const BULK_CONCURRENCY = 3
const BULK_MAX_SELECTION = 25
// How many records we ask Airtable for in one round-trip. The full set is
// streamed into memory on the first paint of the coach worklist; we then
// paginate that buffer locally so the navigator stays predictable
// ("Página X de Y") even while later pages are still in flight.
const AIRTABLE_FETCH_BATCH_SIZE = 100
const PAGE_SIZE_OPTIONS = [25, 50, 100] as const
const DEFAULT_LOCAL_PAGE_SIZE: (typeof PAGE_SIZE_OPTIONS)[number] = 25

function nullableAsNegInfinity(value: number | null | undefined): number {
  return value === null || value === undefined || Number.isNaN(value)
    ? Number.NEGATIVE_INFINITY
    : value
}

function transactionCreatedTimestamp(row: TransactionSummary): number {
  if (!row.created_at) return 0
  const parsed = Date.parse(row.created_at)
  return Number.isNaN(parsed) ? 0 : parsed
}

function compareRows(a: TransactionSummary, b: TransactionSummary, mode: SortMode): number {
  switch (mode) {
    case 'gain_desc':
      return nullableAsNegInfinity(b.capital_gain) - nullableAsNegInfinity(a.capital_gain)
    case 'appreciation_desc':
      return nullableAsNegInfinity(b.appreciation_pct) - nullableAsNegInfinity(a.appreciation_pct)
    case 'value_desc':
      return nullableAsNegInfinity(b.estimated_current_value) - nullableAsNegInfinity(a.estimated_current_value)
    case 'created_desc':
      return transactionCreatedTimestamp(b) - transactionCreatedTimestamp(a)
    case 'created_asc':
    default:
      return transactionCreatedTimestamp(a) - transactionCreatedTimestamp(b)
  }
}

function average(values: Array<number | null | undefined>): number | null {
  const finite = values.filter(
    (value): value is number => value !== null && value !== undefined && Number.isFinite(value),
  )
  if (finite.length === 0) return null
  return finite.reduce((sum, value) => sum + value, 0) / finite.length
}

function TransactionSearchPanel({ onSelect, onUnauthorized }: TransactionSearchPanelProps) {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  // We stream every Airtable batch into a single flat buffer instead of
  // tracking "pages". Local pagination lives entirely in the UI so the
  // navigator can show "Página X de Y" the moment the first page lands and
  // grow Y as the rest of the dataset arrives.
  const [allRows, setAllRows] = useState<TransactionSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [streaming, setStreaming] = useState(false)
  const [allLoaded, setAllLoaded] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Client-side filter + sort state. The whole worklist lives in memory, so
  // doing this in the browser keeps the UX snappy and lets the coach iterate
  // filters without re-querying Airtable.
  const [sortMode, setSortMode] = useState<SortMode>('gain_desc')
  const [minGain, setMinGain] = useState<string>('')
  const [coachFilters, setCoachFilters] = useState<Set<string>>(new Set())
  const [coachDropdownOpen, setCoachDropdownOpen] = useState(false)
  const coachDropdownRef = useRef<HTMLDivElement>(null)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkOpen, setBulkOpen] = useState(false)
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZE_OPTIONS)[number]>(DEFAULT_LOCAL_PAGE_SIZE)
  const [currentPageIndex, setCurrentPageIndex] = useState(0)

  // Close coach dropdown when clicking outside it.
  useEffect(() => {
    if (!coachDropdownOpen) return
    function handleClickOutside(e: MouseEvent) {
      if (coachDropdownRef.current && !coachDropdownRef.current.contains(e.target as Node)) {
        setCoachDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [coachDropdownOpen])

  // Debounce + abort: cancel the previous in-flight request whenever the
  // query changes within SEARCH_DEBOUNCE_MS, so rapid typing never produces
  // a stale "first response wins" race.
  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false
    const handle = window.setTimeout(async () => {
      setLoading(true)
      setStreaming(false)
      setAllLoaded(false)
      setError(null)
      setAllRows([])
      setCurrentPageIndex(0)
      setSelected(new Set())
      let offset: string | null = null
      let isFirst = true
      try {
        do {
          const page = await searchTransactions(query, {
            limit: AIRTABLE_FETCH_BATCH_SIZE,
            offset,
            signal: controller.signal,
          })
          if (cancelled || controller.signal.aborted) return
          setAllRows((current) => [...current, ...page.records])
          if (isFirst) {
            setLoading(false)
            isFirst = false
          }
          offset = page.next_offset
          setStreaming(Boolean(offset))
        } while (offset && !cancelled && !controller.signal.aborted)
        if (!cancelled) {
          setAllLoaded(true)
          setStreaming(false)
        }
      } catch (err) {
        if (cancelled) return
        if ((err as Error).name === 'AbortError') return
        if (err instanceof CoachApiError && err.code === 'unauthorized') {
          onUnauthorized()
          return
        }
        const message =
          err instanceof CoachApiError ? err.message : (err as Error).message
        setError(message || t('coach.search.unknownError'))
      } finally {
        if (!cancelled) {
          setLoading(false)
          setStreaming(false)
        }
      }
    }, SEARCH_DEBOUNCE_MS)
    return () => {
      cancelled = true
      controller.abort()
      window.clearTimeout(handle)
    }
  }, [query, onUnauthorized, t])

  // Distinct coaches discovered in the loaded set. Used both for the filter
  // dropdown and to drive the "coach owner" badges on each row.
  const coachOptions = useMemo(() => {
    const map = new Map<string, string>()
    for (const row of allRows) {
      if (row.coach_id && row.coach_name && !map.has(row.coach_id)) {
        map.set(row.coach_id, row.coach_name)
      }
    }
    return Array.from(map.entries())
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name, 'es'))
  }, [allRows])

  const minGainNumber = useMemo(() => {
    const parsed = Number(minGain)
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null
  }, [minGain])

  const filteredAll = useMemo(() => {
    return allRows
      .filter((row) => {
        if (coachFilters.size > 0 && (!row.coach_id || !coachFilters.has(row.coach_id))) return false
        if (minGainNumber !== null) {
          const gain = row.capital_gain ?? Number.NEGATIVE_INFINITY
          if (gain < minGainNumber) return false
        }
        return true
      })
      .slice()
      .sort((a, b) => compareRows(a, b, sortMode))
  }, [allRows, coachFilters, minGainNumber, sortMode])

  const totalPages = Math.max(1, Math.ceil(filteredAll.length / pageSize))
  const clampedPageIndex = Math.min(currentPageIndex, totalPages - 1)
  const filtered = useMemo(
    () => filteredAll.slice(clampedPageIndex * pageSize, (clampedPageIndex + 1) * pageSize),
    [filteredAll, clampedPageIndex, pageSize],
  )

  // Clamp current page when filters/sort shrink the result set.
  useEffect(() => {
    if (currentPageIndex !== clampedPageIndex) setCurrentPageIndex(clampedPageIndex)
  }, [currentPageIndex, clampedPageIndex])

  // Auto-prune the selection whenever the visible set changes — we don't want
  // a stale id hanging around from a previous filter or a server refresh.
  useEffect(() => {
    setSelected((current) => {
      if (current.size === 0) return current
      const valid = new Set(filtered.map((row) => row.id))
      const next = new Set<string>()
      current.forEach((id) => {
        if (valid.has(id)) next.add(id)
      })
      return next.size === current.size ? current : next
    })
  }, [filtered])

  // Headline stats are computed against the full filtered set so they don't
  // jump around as the coach paginates locally.
  const summary = useMemo(() => {
    let positives = 0
    let totalGain = 0
    const totalCount = filteredAll.length
    for (const row of filteredAll) {
      if (row.capital_gain !== null && row.capital_gain !== undefined) {
        if (row.capital_gain > 0) positives += 1
        totalGain += row.capital_gain
      }
    }
    const avgGain = average(filteredAll.map((row) => row.capital_gain))
    const avgAppreciation = average(filteredAll.map((row) => row.appreciation_pct))
    const avgEstimatedValue = average(filteredAll.map((row) => row.estimated_current_value))
    return { totalCount, positives, totalGain, avgGain, avgAppreciation, avgEstimatedValue }
  }, [filteredAll])

  function handleGoToPage(index: number) {
    const target = Math.max(0, Math.min(totalPages - 1, index))
    if (target === currentPageIndex) return
    setCurrentPageIndex(target)
    setSelected(new Set())
  }

  function toggleSelected(id: string) {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(id)) {
        next.delete(id)
      } else {
        if (next.size >= BULK_MAX_SELECTION) return current
        next.add(id)
      }
      return next
    })
  }

  function toggleSelectAllVisible() {
    setSelected((current) => {
      const allVisibleSelected = filtered.every((row) => current.has(row.id))
      if (allVisibleSelected) {
        const next = new Set(current)
        for (const row of filtered) next.delete(row.id)
        return next
      }
      const next = new Set(current)
      for (const row of filtered) {
        if (next.size >= BULK_MAX_SELECTION) break
        next.add(row.id)
      }
      return next
    })
  }

  const selectedRows = useMemo(
    () => filtered.filter((row) => selected.has(row.id)),
    [filtered, selected],
  )

  const allVisibleSelected =
    filtered.length > 0 && filtered.every((row) => selected.has(row.id))

  const filtersActive = coachFilters.size > 0 || minGainNumber !== null
  const activeFilterCount =
    (coachFilters.size > 0 ? 1 : 0) +
    (minGainNumber !== null ? 1 : 0)

  return (
    <div className="flex flex-col gap-md">
      <Card className="p-md">
        <div className="flex flex-col gap-md md:flex-row md:items-center">
          <div className="flex flex-1 items-center gap-2 rounded-md border border-line bg-surface px-3 py-2">
            <Search className="h-4 w-4 text-ink-muted" aria-hidden />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('coach.search.placeholder')}
              aria-label={t('coach.search.placeholder')}
              className="w-full bg-transparent text-sm text-ink placeholder:text-ink-muted focus:outline-none"
            />
            {loading && <Loader2 className="h-4 w-4 animate-spin text-ink-muted" aria-hidden />}
          </div>

          <div className="flex items-center gap-2">
            {/* Coach owner multi-select dropdown */}
            <div ref={coachDropdownRef} className="relative">
              <button
                type="button"
                onClick={() => setCoachDropdownOpen((o) => !o)}
                className="flex h-10 items-center gap-2 rounded-md border border-line bg-surface px-3 text-sm text-ink shadow-sm transition hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
              >
                <UserCircle2 className="h-4 w-4 text-ink-muted" aria-hidden />
                <span>
                  {coachFilters.size === 0
                    ? 'Todos los coaches'
                    : coachFilters.size === 1
                      ? coachOptions.find((c) => coachFilters.has(c.id))?.name ?? '1 coach'
                      : `${coachFilters.size} coaches`}
                </span>
                {coachFilters.size > 0 && (
                  <span className="flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[10px] font-bold text-white">
                    {coachFilters.size}
                  </span>
                )}
                <ChevronDown className="h-3.5 w-3.5 text-ink-muted" aria-hidden />
              </button>

              {coachDropdownOpen && (
                <div className="absolute right-0 top-full z-30 mt-1 max-h-72 w-56 overflow-y-auto rounded-xl border border-line bg-surface shadow-lift">
                  <label className="flex cursor-pointer items-center gap-2 border-b border-line/60 px-3 py-2.5 text-sm text-ink hover:bg-surface-muted">
                    <input
                      type="checkbox"
                      checked={coachFilters.size === 0}
                      onChange={() => {
                        setCoachFilters(new Set())
                        setCurrentPageIndex(0)
                        setSelected(new Set())
                      }}
                      className="h-4 w-4 rounded border-line accent-primary"
                    />
                    <span className="font-medium">Todos los coaches</span>
                  </label>
                  {coachOptions.map((coach) => (
                    <label
                      key={coach.id}
                      className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm text-ink hover:bg-surface-muted"
                    >
                      <input
                        type="checkbox"
                        checked={coachFilters.has(coach.id)}
                        onChange={() => {
                          setCoachFilters((prev) => {
                            const next = new Set(prev)
                            if (next.has(coach.id)) next.delete(coach.id)
                            else next.add(coach.id)
                            return next
                          })
                          setCurrentPageIndex(0)
                          setSelected(new Set())
                        }}
                        className="h-4 w-4 rounded border-line accent-primary"
                      />
                      {coach.name}
                    </label>
                  ))}
                </div>
              )}
            </div>

            <label className="sr-only" htmlFor="coach-sort">Ordenar</label>
            <select
              id="coach-sort"
              value={sortMode}
              onChange={(e) => setSortMode(e.target.value as SortMode)}
              className="h-10 rounded-md border border-line bg-surface px-3 text-sm text-ink shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
            >
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>

            <Button
              type="button"
              variant={filtersOpen || filtersActive ? 'default' : 'outline'}
              size="sm"
              onClick={() => setFiltersOpen((open) => !open)}
              aria-expanded={filtersOpen}
              aria-controls="coach-filters-panel"
            >
              <Filter className="h-4 w-4" />
              Filtros
              {filtersActive && (
                <span className="ml-1 rounded-full bg-primary/15 px-1.5 py-0.5 text-[10px] font-semibold text-primary">
                  {activeFilterCount}
                </span>
              )}
            </Button>
          </div>
        </div>

        {filtersOpen && (
          <div
            id="coach-filters-panel"
            className="mt-md grid gap-md rounded-2xl border border-line/60 bg-surface-muted p-md md:grid-cols-2"
          >
            <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">
              Capital gain mínimo (€)
              <input
                type="number"
                inputMode="numeric"
                min={0}
                step={1000}
                value={minGain}
                onChange={(e) => setMinGain(e.target.value)}
                placeholder="ej. 10000"
                className="h-10 rounded-md border border-line bg-surface px-3 text-sm font-normal text-ink shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
              />
            </label>
            <div className="flex items-end">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  setMinGain('')
                  setCoachFilters(new Set())
                }}
                disabled={!filtersActive}
                className="text-ink-secondary"
              >
                <X className="h-4 w-4" />
                Limpiar filtros
              </Button>
            </div>
          </div>
        )}
      </Card>

      <div className="grid gap-md md:grid-cols-4">
        <SummaryStat
          icon={Building2}
          label="Transacciones"
          value={summary.totalCount.toString()}
          hint={
            filtersActive
              ? `${allRows.length} en total · filtros aplicados`
              : streaming
                ? `${allRows.length} cargadas · sigue trayendo desde Airtable…`
                : allLoaded
                  ? 'Set completo de Airtable cargado.'
                  : `${allRows.length} cargadas`
          }
        />
        <SummaryStat
          icon={TrendingUp}
          label="Con plusvalía positiva"
          value={`${summary.positives}/${summary.totalCount || 0}`}
          hint="Capital gain estimado mayor que cero según TF Labs."
        />
        <SummaryStat
          icon={BarChart3}
          label="Capital gain agregado"
          value={formatCurrency(summary.totalGain)}
          hint="Suma sobre todas las transacciones filtradas."
          emphasis
        />
        <SummaryStat
          icon={Calculator}
          label="Promedio capital gain"
          value={formatCurrency(summary.avgGain)}
          hint={
            summary.avgAppreciation !== null
              ? `Revalorización media ${formatPercent(summary.avgAppreciation * 100)}`
              : `Valor medio estimado ${formatCurrency(summary.avgEstimatedValue)}`
          }
        />
      </div>

      {streaming && (
        <div
          role="status"
          aria-live="polite"
          className="flex items-center gap-2 rounded-xl border border-primary/20 bg-primary/5 px-md py-2 text-xs text-primary"
        >
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
          Cargando más transacciones desde Airtable… {allRows.length} listas hasta ahora.
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="rounded-xl border border-destructive/30 bg-destructive/5 px-md py-sm text-sm text-destructive"
        >
          {error}
        </div>
      )}

      {selected.size > 0 && (
        <Card className="flex flex-col gap-sm border-primary/30 bg-primary/5 p-md md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-sm">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-sm font-semibold text-white">
              {selected.size}
            </span>
            <div>
              <p className="text-sm font-semibold text-ink">
                {selected.size === 1
                  ? '1 transacción seleccionada'
                  : `${selected.size} transacciones seleccionadas`}
              </p>
              <p className="text-xs text-ink-secondary">
                Se enviará el reporte automático (modo «sin comparables», instantáneo) al inbox de pruebas.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setSelected(new Set())}
              className="text-ink-secondary"
            >
              <X className="h-4 w-4" />
              Limpiar
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={() => setBulkOpen(true)}
              className="rounded-xl shadow-card"
            >
              <Send className="h-4 w-4" />
              Enviar a {selected.size}
            </Button>
          </div>
        </Card>
      )}

      <Card>
        <div className="flex items-center justify-between gap-md border-b border-line/70 px-lg py-sm text-xs uppercase tracking-wide text-ink-muted">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={allVisibleSelected}
              onChange={toggleSelectAllVisible}
              className="h-4 w-4 rounded border-line text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
              aria-label="Seleccionar todas las visibles"
            />
            <span>
              {filtered.length > 0
                ? `Seleccionar ${filtered.length} visibles`
                : 'Sin transacciones'}
            </span>
          </label>
          <span>{selected.size > 0 && `${selected.size}/${BULK_MAX_SELECTION} máx.`}</span>
        </div>
        <ul className="divide-y divide-line/60">
          {!loading && filtered.length === 0 && (
            <li className="px-lg py-2xl text-center text-sm text-ink-secondary">
              {query
                ? t('coach.search.noResults', { query })
                : filtersActive
                  ? 'No hay transacciones que cumplan los filtros actuales.'
                  : t('coach.search.emptyState')}
            </li>
          )}
          {filtered.map((row) => (
            <TransactionRow
              key={row.id}
              row={row}
              selected={selected.has(row.id)}
              onToggle={() => toggleSelected(row.id)}
              onSelect={() => onSelect(row.id)}
            />
          ))}
        </ul>

        {filteredAll.length > 0 && (
          <TransactionPaginator
            currentPage={clampedPageIndex + 1}
            totalPages={totalPages}
            pageSize={pageSize}
            totalRows={filteredAll.length}
            rowStart={clampedPageIndex * pageSize + 1}
            rowEnd={Math.min((clampedPageIndex + 1) * pageSize, filteredAll.length)}
            streaming={streaming}
            onPageChange={handleGoToPage}
            onPageSizeChange={(size) => {
              setPageSize(size)
              setCurrentPageIndex(0)
            }}
          />
        )}
      </Card>

      <BulkSendDialog
        open={bulkOpen}
        onOpenChange={(open) => setBulkOpen(open)}
        rows={selectedRows}
        onClearSelection={() => setSelected(new Set())}
      />
    </div>
  )
}

interface TransactionRowProps {
  row: TransactionSummary
  selected: boolean
  onToggle: () => void
  onSelect: () => void
}

function TransactionRow({ row, selected, onToggle, onSelect }: TransactionRowProps) {
  const appreciation = row.appreciation_pct
  const appreciationPositive =
    appreciation !== null && appreciation !== undefined && appreciation > 0
  const ppm2 = purchasePricePerM2(row)
  // Euro gain: TF Labs estimated current value minus what the client actually paid.
  const eurGain = capitalGain(row.estimated_current_value, totalSpent(row))

  return (
    <li
      className={`group transition ${
        selected ? 'bg-primary/5' : 'hover:bg-surface-muted'
      }`}
    >
      <div className="flex items-stretch gap-md px-lg py-md">
        <label
          className="flex items-center"
          onClick={(event) => event.stopPropagation()}
        >
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            className="h-4 w-4 rounded border-line text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
            aria-label={`Seleccionar ${row.transaction_name}`}
          />
        </label>
        <button
          type="button"
          onClick={onSelect}
          className="flex flex-1 items-center justify-between gap-md text-left focus:outline-none"
        >
          <div className="flex min-w-0 flex-col gap-1">
            <span className="truncate text-sm font-semibold text-ink">
              {row.transaction_name}
            </span>
            <span className="text-xs text-ink-secondary">
              {[row.type, formatDate(row.created_at)].filter(Boolean).join(' · ') || '—'}
            </span>
            <div className="flex flex-wrap items-center gap-2 pt-1">
              {row.coach_name && (
                <span className="inline-flex items-center gap-1 rounded-full bg-surface-muted px-2 py-0.5 text-[11px] font-medium text-ink-secondary">
                  <UserCircle2 className="h-3 w-3" aria-hidden />
                  {row.coach_name}
                </span>
              )}
              {row.appreciation_town_name && (
                <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
                  <MapPin className="h-3 w-3" aria-hidden />
                  {row.appreciation_town_name}
                </span>
              )}
              {row.real_settlement_date && (
                <span className="text-[11px] text-ink-muted">
                  Firma: {formatDate(row.real_settlement_date)}
                </span>
              )}
            </div>
          </div>
          <div className="hidden shrink-0 items-baseline gap-md text-right md:flex">
            <div className="flex flex-col">
              <span className="text-xs uppercase tracking-wide text-ink-muted">Total pagado</span>
              <span className="text-sm font-semibold text-ink">
                {formatCurrency(totalSpent(row))}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs uppercase tracking-wide text-ink-muted">€/m² compra</span>
              <span className="text-sm font-semibold text-ink">
                {formatPricePerM2(ppm2)}
              </span>
            </div>
            <div className="flex flex-col items-end">
              <span className="text-xs uppercase tracking-wide text-ink-muted">Plusvalía</span>
              <span
                className={`text-sm font-semibold leading-tight ${
                  appreciationPositive ? 'text-emerald-700' : 'text-ink-muted'
                }`}
              >
                {appreciation !== null && appreciation !== undefined
                  ? formatPercent(appreciation * 100)
                  : '—'}
              </span>
              {eurGain !== null && (
                <span className={`text-xs font-medium ${appreciationPositive ? 'text-emerald-600' : 'text-ink-secondary'}`}>
                  {formatCurrency(eurGain)}
                </span>
              )}
            </div>
          </div>
        </button>
      </div>
      <div className="grid grid-cols-2 gap-2 px-lg pb-md text-right md:hidden">
        <div>
          <span className="block text-[11px] uppercase tracking-wide text-ink-muted">Pagado</span>
          <span className="text-sm font-semibold text-ink">
            {formatCurrency(totalSpent(row))}
          </span>
        </div>
        <div>
          <span className="block text-[11px] uppercase tracking-wide text-ink-muted">Plusvalía</span>
          <span className={`text-sm font-semibold leading-tight ${appreciationPositive ? 'text-emerald-700' : 'text-ink-muted'}`}>
            {appreciation !== null && appreciation !== undefined
              ? formatPercent(appreciation * 100)
              : '—'}
          </span>
          {eurGain !== null && (
            <span className={`block text-xs font-medium ${appreciationPositive ? 'text-emerald-600' : 'text-ink-secondary'}`}>
              {formatCurrency(eurGain)}
            </span>
          )}
        </div>
      </div>
    </li>
  )
}

interface SummaryStatProps {
  icon: LucideIcon
  label: string
  value: string
  hint?: string
  emphasis?: boolean
}

function SummaryStat({ icon: Icon, label, value, hint, emphasis }: SummaryStatProps) {
  return (
    <Card className="flex items-start gap-3 p-md">
      <span
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${
          emphasis ? 'bg-primary/10 text-primary' : 'bg-surface-muted text-ink-secondary'
        }`}
      >
        <Icon className="h-4 w-4" aria-hidden />
      </span>
      <div className="min-w-0">
        <p className="text-xs uppercase tracking-wide text-ink-muted">{label}</p>
        <p className={`mt-1 text-lg font-semibold ${emphasis ? 'text-primary' : 'text-ink'}`}>
          {value}
        </p>
        {hint && <p className="mt-1 text-[11px] leading-snug text-ink-muted">{hint}</p>}
      </div>
    </Card>
  )
}

interface TransactionPaginatorProps {
  currentPage: number
  totalPages: number
  pageSize: number
  totalRows: number
  rowStart: number
  rowEnd: number
  streaming: boolean
  onPageChange: (index: number) => void
  onPageSizeChange: (size: (typeof PAGE_SIZE_OPTIONS)[number]) => void
}

// Footer-style paginator that lives inside the list Card. Designed to look
// and behave like the shadcn DataTable example: row-count copy on the left,
// page-size selector + Anterior / Página X de Y / Siguiente on the right.
// The page chip set is windowed (max 7 visible) with ellipsis so even very
// large coaches (50+ pages) don't blow up the layout.
function TransactionPaginator({
  currentPage,
  totalPages,
  pageSize,
  totalRows,
  rowStart,
  rowEnd,
  streaming,
  onPageChange,
  onPageSizeChange,
}: TransactionPaginatorProps) {
  const pageNumbers = buildPaginationWindow(currentPage, totalPages)
  return (
    <div className="flex flex-col gap-md border-t border-line/70 bg-surface-muted/40 px-lg py-md md:flex-row md:items-center md:justify-between">
      <div className="text-xs text-ink-secondary">
        Mostrando <span className="font-semibold text-ink">{rowStart.toLocaleString('es-ES')}</span>
        {' – '}
        <span className="font-semibold text-ink">{rowEnd.toLocaleString('es-ES')}</span>
        {' de '}
        <span className="font-semibold text-ink">{totalRows.toLocaleString('es-ES')}</span>
        {' transacciones'}
        {streaming && (
          <span className="ml-2 inline-flex items-center gap-1 text-primary">
            <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
            actualizándose…
          </span>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-md">
        <label className="flex items-center gap-2 text-xs uppercase tracking-wide text-ink-muted">
          Filas por página
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value) as (typeof PAGE_SIZE_OPTIONS)[number])}
            className="h-8 rounded-md border border-line bg-surface px-2 text-xs font-medium text-ink shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
          >
            {PAGE_SIZE_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="h-8 w-8"
            onClick={() => onPageChange(currentPage - 2)}
            disabled={currentPage === 1}
            aria-label="Página anterior"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>

          {pageNumbers.map((item, idx) =>
            item === 'ellipsis' ? (
              <span
                key={`gap-${idx}`}
                className="px-1 text-xs text-ink-muted"
                aria-hidden
              >
                …
              </span>
            ) : (
              <Button
                key={item}
                type="button"
                variant={item === currentPage ? 'default' : 'outline'}
                size="sm"
                className="h-8 min-w-8 px-2 text-xs"
                onClick={() => onPageChange(item - 1)}
                aria-current={item === currentPage ? 'page' : undefined}
                aria-label={`Ir a la página ${item}`}
              >
                {item}
              </Button>
            ),
          )}

          <Button
            type="button"
            variant="outline"
            size="icon"
            className="h-8 w-8"
            onClick={() => onPageChange(currentPage)}
            disabled={currentPage >= totalPages}
            aria-label="Página siguiente"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}

// Build a compact paginator window: always show first, last, current and its
// two neighbours, with "ellipsis" sentinels filling the gaps. Keeps the
// control to ≤7 buttons regardless of total page count.
function buildPaginationWindow(
  currentPage: number,
  totalPages: number,
): Array<number | 'ellipsis'> {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, idx) => idx + 1)
  }
  const window: Array<number | 'ellipsis'> = [1]
  const start = Math.max(2, currentPage - 1)
  const end = Math.min(totalPages - 1, currentPage + 1)
  if (start > 2) window.push('ellipsis')
  for (let page = start; page <= end; page += 1) window.push(page)
  if (end < totalPages - 1) window.push('ellipsis')
  window.push(totalPages)
  return window
}

type BulkItemStatus = 'drafting' | 'ready' | 'sending' | 'sent' | 'skipped' | 'failed'

interface BulkEmailDraft {
  preview: CoachAutoEmailPreviewResponse
  subject: string
  body: string
}

interface BulkItemState {
  status: BulkItemStatus
  message?: string
}

interface BulkSendDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  rows: TransactionSummary[]
  onClearSelection: () => void
}

// Bulk-send modal. The important guardrail: selected transactions are first
// converted into editable email/PDF drafts, and only then can the coach send.
// This keeps weird no-scrape valuations visible before they reach a client.
function BulkSendDialog({ open, onOpenChange, rows, onClearSelection }: BulkSendDialogProps) {
  const [running, setRunning] = useState(false)
  const [drafting, setDrafting] = useState(false)
  const [done, setDone] = useState(false)
  const [progress, setProgress] = useState<Record<string, BulkItemState>>({})
  const [drafts, setDrafts] = useState<Record<string, BulkEmailDraft>>({})
  const [activeId, setActiveId] = useState<string | null>(null)
  const [pdfPreviewing, setPdfPreviewing] = useState(false)
  const [pdfPreviewError, setPdfPreviewError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const pdfUrlRef = useRef<string | null>(null)

  // Reset progress whenever the dialog is reopened with a fresh selection.
  useEffect(() => {
    if (open) {
      setRunning(false)
      setDrafting(false)
      setDone(false)
      setDrafts({})
      setActiveId(rows[0]?.id ?? null)
      setPdfPreviewError(null)
      const initial: Record<string, BulkItemState> = {}
      for (const row of rows) initial[row.id] = { status: 'drafting' }
      setProgress(initial)
      void prepareDrafts()
    } else {
      abortRef.current?.abort()
      abortRef.current = null
      if (pdfUrlRef.current) URL.revokeObjectURL(pdfUrlRef.current)
      pdfUrlRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, rows])

  async function prepareDrafts() {
    if (rows.length === 0) return
    setDrafting(true)
    const controller = new AbortController()
    abortRef.current = controller
    let index = 0
    const queue = rows.slice()

    function updateStatus(id: string, patch: Partial<BulkItemState>) {
      setProgress((current) => ({
        ...current,
        [id]: { ...current[id], ...patch },
      }))
    }

    async function worker() {
      while (true) {
        const row = queue[index]
        index += 1
        if (!row || controller.signal.aborted) return
        updateStatus(row.id, { status: 'drafting', message: 'Generando email y reporte…' })
        try {
          const preview = await previewTransactionAutoEmail(row.id, { signal: controller.signal })
          setDrafts((current) => ({
            ...current,
            [row.id]: {
              preview,
              subject: preview.subject,
              body: preview.body,
            },
          }))
          updateStatus(row.id, {
            status: preview.client_email ? 'ready' : 'skipped',
            message: preview.review_warning ?? 'Listo para revisar',
          })
        } catch (err) {
          if ((err as Error).name === 'AbortError') return
          const message =
            err instanceof CoachApiError ? err.detail ?? err.message : (err as Error).message
          updateStatus(row.id, { status: 'failed', message: message || 'Error preparando draft' })
        }
      }
    }

    const workers = Array.from({ length: Math.min(BULK_CONCURRENCY, rows.length) }, () => worker())
    await Promise.all(workers)
    setDrafting(false)
    abortRef.current = null
  }

  function updateDraft(id: string, patch: Partial<Pick<BulkEmailDraft, 'subject' | 'body'>>) {
    setDrafts((current) => {
      const draft = current[id]
      if (!draft) return current
      return { ...current, [id]: { ...draft, ...patch } }
    })
  }

  async function previewPdf(draft: BulkEmailDraft) {
    setPdfPreviewing(true)
    setPdfPreviewError(null)
    try {
      const payload: ReportPdfPayload = {
        request: draft.preview.valuation_request,
        valuation: draft.preview.valuation,
        transaction: draft.preview.transaction,
        includeComparables: false,
      }
      const url = await createReportPdfObjectUrl(payload)
      if (pdfUrlRef.current) URL.revokeObjectURL(pdfUrlRef.current)
      pdfUrlRef.current = url
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch (err) {
      setPdfPreviewError(err instanceof Error ? err.message : 'No se pudo abrir el PDF')
    } finally {
      setPdfPreviewing(false)
    }
  }

  async function runBulk() {
    if (running || drafting || rows.length === 0) return
    setRunning(true)
    setDone(false)
    const controller = new AbortController()
    abortRef.current = controller

    let index = 0
    const queue = rows.slice()

    function updateStatus(id: string, patch: Partial<BulkItemState>) {
      setProgress((current) => ({
        ...current,
        [id]: { ...current[id], ...patch },
      }))
    }

    async function worker() {
      while (true) {
        const row = queue[index]
        index += 1
        if (!row || controller.signal.aborted) return
        const draft = drafts[row.id]
        if (!draft?.preview.client_email) {
          updateStatus(row.id, { status: 'skipped', message: 'Sin email cliente' })
          continue
        }
        updateStatus(row.id, { status: 'sending' })
        try {
          const response = await sendTransactionEmail(row.id, {
            to: draft.preview.client_email,
            subject: draft.subject,
            body: draft.body,
            valuation_request: draft.preview.valuation_request,
            valuation: draft.preview.valuation,
            transaction: draft.preview.transaction,
            include_comparables: false,
          })
          updateStatus(row.id, {
            status: response.sent ? 'sent' : 'skipped',
            message: response.sent
              ? `Enviado → ${draft.preview.delivered_to ?? draft.preview.client_email}`
              : response.message,
          })
        } catch (err) {
          if ((err as Error).name === 'AbortError') return
          const message =
            err instanceof CoachApiError ? err.detail ?? err.message : (err as Error).message
          updateStatus(row.id, { status: 'failed', message: message || 'Error desconocido' })
        }
      }
    }

    const workers = Array.from({ length: Math.min(BULK_CONCURRENCY, rows.length) }, () => worker())
    await Promise.all(workers)
    setRunning(false)
    setDone(true)
    abortRef.current = null
  }

  const counts = useMemo(() => {
    let pending = 0
    let ready = 0
    let sending = 0
    let sent = 0
    let skipped = 0
    let failed = 0
    for (const row of rows) {
      const state = progress[row.id]?.status ?? 'drafting'
      if (state === 'drafting') pending += 1
      if (state === 'ready') ready += 1
      if (state === 'sending') sending += 1
      if (state === 'sent') sent += 1
      if (state === 'skipped') skipped += 1
      if (state === 'failed') failed += 1
    }
    return { pending, ready, sending, sent, skipped, failed }
  }, [rows, progress])

  const activeRow = rows.find((row) => row.id === activeId) ?? rows[0] ?? null
  const activeDraft = activeRow ? drafts[activeRow.id] : null
  const readyCount = rows.filter((row) => progress[row.id]?.status === 'ready').length
  const canSend = readyCount > 0 && !running && !drafting && !done

  function handleClose() {
    abortRef.current?.abort()
    onOpenChange(false)
    if (done) onClearSelection()
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (running || drafting || nextOpen) return
        handleClose()
      }}
    >
      <DialogContent
        className="sm:max-w-5xl"
        onInteractOutside={(event) => {
          if (running || drafting) event.preventDefault()
        }}
        onEscapeKeyDown={(event) => {
          if (running || drafting) event.preventDefault()
        }}
      >
        <DialogHeader>
          <DialogTitle>Revisar antes de enviar</DialogTitle>
          <DialogDescription>
            Primero generamos el email y el PDF en modo «sin comparables». Revisa el
            contenido y los avisos; solo después se habilita el envío. En local se
            enruta al inbox de pruebas configurado en{' '}
            <code className="rounded bg-surface-muted px-1 text-xs">RESEND_TEST_TO</code>.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-2 rounded-2xl border border-line bg-surface-muted p-md md:grid-cols-6">
          <BulkCounter label="Preparando" value={counts.pending} tone="active" />
          <BulkCounter label="Listos" value={counts.ready} tone="success" />
          <BulkCounter label="Enviando" value={counts.sending} tone="active" />
          <BulkCounter label="Enviados" value={counts.sent} tone="success" />
          <BulkCounter label="Omitidos" value={counts.skipped} tone="warn" />
          <BulkCounter label="Fallidos" value={counts.failed} tone="error" />
        </div>

        <div className="grid gap-md lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.3fr)]">
          <div className="max-h-[520px] overflow-y-auto rounded-2xl border border-line">
            <ul className="divide-y divide-line/70">
              {rows.map((row) => {
                const state = progress[row.id] ?? { status: 'drafting' as BulkItemStatus }
                const draft = drafts[row.id]
                const active = activeRow?.id === row.id
                return (
                  <li key={row.id}>
                    <button
                      type="button"
                      onClick={() => setActiveId(row.id)}
                      className={`flex w-full items-center gap-md px-md py-sm text-left transition ${
                        active ? 'bg-primary/5' : 'hover:bg-surface-muted'
                      }`}
                    >
                      <BulkStatusBadge status={state.status} />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-ink">
                          {row.transaction_name}
                        </p>
                        <p className="truncate text-xs text-ink-secondary">
                          {draft?.preview.delivered_to ?? row.client_email ?? 'Sin email cliente'}
                          {state.message ? ` · ${state.message}` : ''}
                        </p>
                      </div>
                      <span
                        className={`hidden text-xs font-medium sm:inline ${
                          (draft?.preview.capital_gain ?? row.capital_gain ?? 0) < 0
                            ? 'text-destructive'
                            : 'text-ink-muted'
                        }`}
                      >
                        {draft
                          ? formatCurrency(draft.preview.capital_gain)
                          : row.capital_gain !== null && row.capital_gain !== undefined
                            ? formatCurrency(row.capital_gain)
                            : '—'}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>

          <div className="min-h-[520px] rounded-2xl border border-line bg-surface p-md">
            {!activeDraft ? (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-sm text-ink-secondary">
                <Loader2 className="h-5 w-5 animate-spin text-primary" aria-hidden />
                Preparando el borrador para revisar…
              </div>
            ) : (
              <div className="flex h-full flex-col gap-md">
                {activeDraft.preview.review_warning && (
                  <div className="rounded-xl border border-amber-300 bg-amber-50 px-md py-sm text-sm text-amber-800">
                    <div className="flex items-start gap-2">
                      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                      <p>{activeDraft.preview.review_warning}</p>
                    </div>
                  </div>
                )}

                <div className="grid gap-2 rounded-xl border border-line/70 bg-surface-muted p-sm text-xs md:grid-cols-3">
                  <div>
                    <p className="font-semibold uppercase tracking-wide text-ink-muted">Destino</p>
                    <p className="truncate text-ink">{activeDraft.preview.delivered_to ?? '—'}</p>
                  </div>
                  <div>
                    <p className="font-semibold uppercase tracking-wide text-ink-muted">Estimado</p>
                    <p className="text-ink">{formatCurrency(activeDraft.preview.estimated_value)}</p>
                  </div>
                  <div>
                    <p className="font-semibold uppercase tracking-wide text-ink-muted">Ganancia vs compra</p>
                    <p className={(activeDraft.preview.capital_gain ?? 0) < 0 ? 'text-destructive' : 'text-ink'}>
                      {formatCurrency(activeDraft.preview.capital_gain)}
                    </p>
                  </div>
                </div>

                <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                  Asunto
                  <input
                    value={activeDraft.subject}
                    onChange={(event) => updateDraft(activeDraft.preview.transaction_id, { subject: event.target.value })}
                    className="h-10 rounded-md border border-line bg-surface px-3 text-sm font-normal normal-case tracking-normal text-ink shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
                  />
                </label>

                <label className="flex min-h-0 flex-1 flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                  Cuerpo del email
                  <textarea
                    value={activeDraft.body}
                    onChange={(event) => updateDraft(activeDraft.preview.transaction_id, { body: event.target.value })}
                    className="min-h-64 flex-1 resize-none rounded-md border border-line bg-surface p-3 text-sm font-normal normal-case leading-relaxed tracking-normal text-ink shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
                  />
                </label>

                {pdfPreviewError && (
                  <p className="rounded-lg bg-destructive/5 px-sm py-2 text-xs text-destructive">
                    {pdfPreviewError}
                  </p>
                )}

                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-xs text-ink-muted">
                    PDF adjunto: <span className="font-medium text-ink">prophero-valoracion-{activeDraft.preview.transaction_id}.pdf</span>
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => previewPdf(activeDraft)}
                    disabled={pdfPreviewing}
                  >
                    {pdfPreviewing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
                    Ver PDF
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-sm md:flex-row md:items-center md:justify-between">
          <p className="text-xs text-ink-muted">
            Los reportes generados no scrapean Idealista. Si ves ganancia negativa o un municipio raro,
            abre el PDF y revisa la transacción antes de enviarla.
          </p>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleClose}
              disabled={running || drafting}
              className="text-ink-secondary"
            >
              {done ? 'Cerrar' : 'Cancelar'}
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={runBulk}
              disabled={!canSend}
              className="rounded-xl shadow-card"
            >
              {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              {running
                ? 'Enviando…'
                : drafting
                  ? 'Preparando…'
                  : done
                    ? 'Completado'
                    : `Enviar ${readyCount} revisados`}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

interface BulkCounterProps {
  label: string
  value: number
  tone: 'muted' | 'active' | 'success' | 'warn' | 'error'
}

function BulkCounter({ label, value, tone }: BulkCounterProps) {
  const toneClass = {
    muted: 'text-ink-secondary',
    active: 'text-primary',
    success: 'text-emerald-700',
    warn: 'text-amber-700',
    error: 'text-destructive',
  }[tone]
  return (
    <div className="flex flex-col items-center justify-center rounded-xl bg-surface px-2 py-2 text-center">
      <span className={`text-lg font-semibold ${toneClass}`}>{value}</span>
      <span className="text-[10px] font-semibold uppercase tracking-wide text-ink-muted">
        {label}
      </span>
    </div>
  )
}

function BulkStatusBadge({ status }: { status: BulkItemStatus }) {
  if (status === 'sent')
    return (
      <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
        <CheckCircle2 className="h-4 w-4" />
      </span>
    )
  if (status === 'sending')
    return (
      <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
        <Loader2 className="h-4 w-4 animate-spin" />
      </span>
    )
  if (status === 'failed')
    return (
      <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-destructive/10 text-destructive">
        <AlertCircle className="h-4 w-4" />
      </span>
    )
  if (status === 'skipped')
    return (
      <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-700">
        <AlertCircle className="h-4 w-4" />
      </span>
    )
  return (
    <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-surface-muted text-ink-muted">
      <FileText className="h-4 w-4" />
    </span>
  )
}

interface TransactionDetailPanelProps {
  transactionId: string
  onBack: () => void
  onUnauthorized: () => void
}

type ReportFlowView = 'setup' | 'report' | 'composer'

function TransactionDetailPanel({
  transactionId,
  onBack,
  onUnauthorized,
}: TransactionDetailPanelProps) {
  const { t } = useTranslation()
  const [data, setData] = useState<TransactionDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [valuationResult, setValuationResult] =
    useState<CoachTransactionValuationResponse | null>(null)
  const [valuationLoading, setValuationLoading] = useState(false)
  const [valuationError, setValuationError] = useState<string | null>(null)
  // Toggle for the "Generar reporte" CTA: when false we skip the Idealista
  // scrape and the report is built from the TF Labs municipal €/m² instead.
  // Coaches who don't need fresh comparables save ~60s and one Bright Data
  // session every time they click.
  const [includeComparables, setIncludeComparables] = useState(true)
  const [reportView, setReportView] = useState<ReportFlowView>('setup')
  const generationRef = useRef<HTMLDivElement | null>(null)
  const reportRef = useRef<HTMLDivElement | null>(null)
  const composerRef = useRef<HTMLDivElement | null>(null)
  const composerUnlocked = Boolean(valuationResult) && reportView === 'composer'

  useEffect(() => {
    const controller = new AbortController()
    getTransaction(transactionId, { signal: controller.signal })
      .then(setData)
      .catch((err) => {
        if ((err as Error).name === 'AbortError') return
        if (err instanceof CoachApiError && err.code === 'unauthorized') {
          onUnauthorized()
          return
        }
        const message =
          err instanceof CoachApiError ? err.message : (err as Error).message
        setError(message || t('coach.detail.unknownError'))
      })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [transactionId, onUnauthorized, t])

  useEffect(() => {
    if (valuationLoading) {
      generationRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [valuationLoading])

  useEffect(() => {
    if (reportView === 'report') {
      reportRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [reportView])

  useEffect(() => {
    if (composerUnlocked) {
      composerRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [composerUnlocked])

  const acquisitionCostRows = useMemo(() => {
    if (!data) return []
    return acquisitionCosts(data).filter((row) => row.value !== null && row.value !== undefined)
  }, [data])

  async function handleGenerateValuation() {
    if (valuationLoading) return
    setValuationLoading(true)
    setValuationError(null)
    setValuationResult(null)
    setReportView('setup')
    try {
      const response = await generateTransactionValuation(transactionId, {
        includeComparables,
      })
      setValuationResult(response)
      setReportView('report')
    } catch (err) {
      const message =
        err instanceof CoachApiError ? err.detail ?? err.message : (err as Error).message
      setValuationError(message || t('coach.valuation.unknownError'))
    } finally {
      setValuationLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-md">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={onBack}
        className="self-start text-ink-secondary"
      >
        <ArrowLeft className="h-4 w-4" />
        {t('coach.detail.back')}
      </Button>

      {loading && (
        <Card className="flex items-center gap-2 px-lg py-md text-sm text-ink-secondary">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t('coach.detail.loading')}
        </Card>
      )}

      {error && (
        <div
          role="alert"
          className="rounded-xl border border-destructive/30 bg-destructive/5 px-md py-sm text-sm text-destructive"
        >
          {error}
        </div>
      )}

      {data && (
        <>
          <Card className="p-lg md:p-xl">
            <h2 className="text-2xl font-semibold tracking-tight text-ink">
              {data.transaction_name}
            </h2>
            <p className="mt-1 text-sm text-ink-secondary">
              {[data.type, formatDate(data.created_at)].filter(Boolean).join(' · ') || '—'}
            </p>
          </Card>

          <ReportGenerationFlow
            valuationLoading={valuationLoading}
            valuationReady={Boolean(valuationResult)}
            composerUnlocked={composerUnlocked}
          />
          <CoachReportLoadingDialog open={valuationLoading} />

          {reportView === 'report' && valuationResult && (
            <div ref={reportRef} className="grid gap-md">
              <div className="flex items-center justify-between gap-sm">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setReportView('setup')}
                  className="text-ink-secondary"
                >
                  <ArrowLeft className="h-4 w-4" />
                  Atrás
                </Button>
              </div>
              <CoachInvestorReport
                transaction={data}
                valuationResult={valuationResult}
              />
              <Card className="p-md md:p-lg">
                <CoachReportPdfPreview
                  valuationResult={valuationResult}
                  variant="report"
                />
              </Card>
              <Card className="flex flex-col gap-md border-primary/20 bg-primary/5 p-lg md:flex-row md:items-center md:justify-between md:p-xl">
                <div>
                  <p className="text-sm font-semibold text-ink">Reporte revisado</p>
                  <p className="mt-1 max-w-2xl text-sm text-ink-secondary">
                    Cuando el rango, la plusvalía y los comparables estén correctos, continúa al
                    editor del mensaje para preparar el envío al cliente.
                  </p>
                </div>
                <Button
                  type="button"
                  size="lg"
                  onClick={() => setReportView('composer')}
                  className="w-full rounded-xl shadow-card transition-shadow hover:shadow-lift sm:w-auto"
                >
                  Continuar a email
                  <Send className="h-4 w-4" />
                </Button>
              </Card>
            </div>
          )}

          {composerUnlocked && valuationResult && (
            <div ref={composerRef} className="grid gap-md">
              <div>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setReportView('report')}
                  className="text-ink-secondary"
                >
                  <ArrowLeft className="h-4 w-4" />
                  Atrás al reporte
                </Button>
              </div>
              <CoachClientReportComposer
                transaction={data}
                valuationResult={valuationResult}
              />
            </div>
          )}

          {(!valuationResult || reportView === 'setup') && (
            <>
              <Card className="p-lg md:p-xl">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-secondary">
                  {t('coach.detail.clientTitle')}
                </h3>
                <dl className="mt-md grid grid-cols-1 gap-md md:grid-cols-3">
                  <Metric
                    label={t('coach.fields.clientName')}
                    value={clientName(data.transaction_name)}
                  />
                  <Metric
                    label={t('coach.fields.clientEmail')}
                    value={
                      data.client_email ? (
                        <a
                          href={`mailto:${data.client_email}`}
                          className="break-all text-primary underline-offset-2 hover:underline"
                        >
                          {data.client_email}
                        </a>
                      ) : (
                        '—'
                      )
                    }
                  />
                  <Metric
                    label={t('coach.fields.settlementDate')}
                    value={formatDate(data.real_settlement_date)}
                  />
                </dl>
              </Card>

              <Card className="p-lg md:p-xl">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-secondary">
                  {t('coach.detail.propertyTitle')}
                </h3>
                <dl className="mt-md grid grid-cols-1 gap-md md:grid-cols-2">
                  <Metric label={t('coach.fields.address')} value={data.address ?? '—'} />
                  <Metric
                    label={t('coach.fields.cadastralReference')}
                    value={
                      data.cadastral_reference ? (
                        <span className="font-mono text-sm">{data.cadastral_reference}</span>
                      ) : (
                        '—'
                      )
                    }
                  />
                </dl>
                <dl className="mt-md grid grid-cols-2 gap-md md:grid-cols-4">
                  <Metric label={t('coach.fields.type')} value={data.type ?? '—'} />
                  <Metric label={t('coach.fields.bedrooms')} value={formatNumber(data.bedrooms)} />
                  <Metric label={t('coach.fields.bathrooms')} value={formatNumber(data.bathrooms)} />
                  <Metric
                    label={t('coach.fields.landsize')}
                    value={formatNumber(data.landsize_m2, ' m²')}
                  />
                </dl>
              </Card>

              <Card className="p-lg md:p-xl">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-secondary">
                  {t('coach.detail.financialsTitle')}
                </h3>
                <dl className="mt-md grid grid-cols-1 gap-md md:grid-cols-3">
                  <Metric
                    label={t('coach.fields.finalTotalPrice')}
                    value={formatCurrency(data.final_total_price)}
                    emphasis
                  />
                  <Metric
                    label={t('coach.fields.price')}
                    value={formatCurrency(data.price)}
                  />
                  <Metric
                    label="€/m² compra"
                    value={formatPricePerM2(purchasePricePerM2(data))}
                  />
                </dl>
                {acquisitionCostRows.length > 0 && (
                  <div className="mt-lg rounded-2xl border border-line bg-surface-muted p-md">
                    <p className="text-sm font-semibold text-ink">Desglose incluido en el precio final</p>
                    <dl className="mt-md grid grid-cols-2 gap-3 md:grid-cols-4">
                      {acquisitionCostRows.map((row) => (
                        <div key={row.label}>
                          <dt className="text-xs uppercase tracking-wide text-ink-muted">{row.label}</dt>
                          <dd className="text-sm font-semibold text-ink">{formatCurrency(row.value)}</dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                )}
              </Card>

              <Card ref={generationRef} className="p-lg md:p-xl">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-secondary">
                  {t('coach.valuation.title')}
                </h3>
                <p className="mt-2 text-sm text-ink-secondary">
                  {t('coach.valuation.description')}
                </p>
                {valuationError && (
                  <div
                    role="alert"
                    className="mt-md rounded-xl border border-destructive/30 bg-destructive/5 px-md py-sm text-sm text-destructive"
                  >
                    {valuationError}
                  </div>
                )}

                {!valuationResult && (
                  <div className="mt-md flex flex-col gap-sm">
                    <p className="text-xs font-semibold uppercase tracking-wide text-ink-secondary">
                      {t('coach.valuation.variantLabel')}
                    </p>
                    <div
                      role="radiogroup"
                      aria-label={t('coach.valuation.variantLabel')}
                      className="inline-flex w-full gap-1 rounded-2xl border border-line/60 bg-surface-muted p-1 sm:w-auto"
                    >
                      <button
                        type="button"
                        role="radio"
                        aria-checked={includeComparables}
                        onClick={() => setIncludeComparables(true)}
                        disabled={valuationLoading}
                        className={`flex-1 rounded-xl px-md py-sm text-sm font-semibold transition-all duration-fast focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 disabled:cursor-not-allowed disabled:opacity-50 sm:flex-none ${
                          includeComparables
                            ? 'bg-surface text-ink shadow-card ring-1 ring-line/40'
                            : 'text-ink-muted hover:text-ink'
                        }`}
                      >
                        {t('coach.valuation.variantWith')}
                      </button>
                      <button
                        type="button"
                        role="radio"
                        aria-checked={!includeComparables}
                        onClick={() => setIncludeComparables(false)}
                        disabled={valuationLoading}
                        className={`flex-1 rounded-xl px-md py-sm text-sm font-semibold transition-all duration-fast focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 disabled:cursor-not-allowed disabled:opacity-50 sm:flex-none ${
                          !includeComparables
                            ? 'bg-surface text-ink shadow-card ring-1 ring-line/40'
                            : 'text-ink-muted hover:text-ink'
                        }`}
                      >
                        {t('coach.valuation.variantWithout')}
                      </button>
                    </div>
                    <p className="text-xs leading-relaxed text-ink-muted">
                      {includeComparables
                        ? t('coach.valuation.variantWithHint')
                        : t('coach.valuation.variantWithoutHint')}
                    </p>
                  </div>
                )}

                <div className="mt-lg flex flex-col gap-sm sm:flex-row sm:items-center sm:gap-md">
                  <Button
                    type="button"
                    size="lg"
                    onClick={() => {
                      if (valuationResult) {
                        setReportView('report')
                        return
                      }
                      void handleGenerateValuation()
                    }}
                    disabled={valuationLoading}
                    className="w-full rounded-xl px-lg font-semibold shadow-card transition-shadow hover:shadow-lift focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 sm:w-auto"
                  >
                    {valuationLoading ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : valuationResult ? (
                      <FileText className="h-4 w-4" />
                    ) : (
                      <Sparkles className="h-4 w-4" />
                    )}
                    {valuationLoading
                      ? t('coach.valuation.generating')
                      : valuationResult
                        ? 'Ver reporte generado'
                        : t('coach.valuation.cta')}
                  </Button>
                  {!valuationResult && !valuationLoading && (
                    <p className="text-xs text-ink-muted">
                      {includeComparables
                        ? 'Tarda ~60s · scraping en vivo'
                        : 'Instantáneo · sin scraping'}
                    </p>
                  )}
                </div>
              </Card>
            </>
          )}
        </>
      )}
    </div>
  )
}

interface ReportGenerationFlowProps {
  valuationLoading: boolean
  valuationReady: boolean
  composerUnlocked: boolean
}

function ReportGenerationFlow({
  valuationLoading,
  valuationReady,
  composerUnlocked,
}: ReportGenerationFlowProps) {
  const steps = [
    {
      label: 'Datos revisados',
      description: 'Transacción y costes cargados desde Airtable.',
      icon: CheckCircle2,
      status: 'done',
    },
    {
      label: 'Generar reporte',
      description: valuationLoading ? 'Calculando mercado y rango conservador…' : 'Listo para lanzar la valoración.',
      icon: Loader2,
      status: valuationLoading ? 'active' : valuationReady ? 'done' : 'active',
    },
    {
      label: 'Revisar informe',
      description: valuationReady ? 'Reporte inversor disponible para validar.' : 'Aparecerá cuando termine la generación.',
      icon: FileText,
      status: valuationReady ? (composerUnlocked ? 'done' : 'active') : 'pending',
    },
    {
      label: 'Editar y enviar',
      description: composerUnlocked ? 'Editor abierto con el relato del cliente.' : 'Se desbloquea tras revisar el reporte.',
      icon: MailCheck,
      status: composerUnlocked ? 'active' : 'pending',
    },
  ] as const

  return (
    <Card className="p-md md:p-lg">
      <div className="grid gap-sm md:grid-cols-4">
        {steps.map((step, index) => {
          const Icon = step.icon
          const isActive = step.status === 'active'
          const isDone = step.status === 'done'

          return (
            <div
              key={step.label}
              className={`rounded-2xl border p-md transition ${
                isActive
                  ? 'border-primary/40 bg-primary/5'
                  : isDone
                    ? 'border-emerald-200 bg-emerald-50/40'
                    : 'border-line bg-surface'
              }`}
            >
              <div className="flex items-center gap-sm">
                <div
                  className={`flex h-8 w-8 items-center justify-center rounded-full ${
                    isActive
                      ? 'bg-primary text-white'
                      : isDone
                        ? 'bg-emerald-600 text-white'
                        : 'bg-surface-muted text-ink-muted'
                  }`}
                >
                  <Icon className={`h-4 w-4 ${step.label === 'Generar reporte' && valuationLoading ? 'animate-spin' : ''}`} />
                </div>
                <span className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
                  Paso {index + 1}
                </span>
              </div>
              <p className="mt-3 text-sm font-semibold text-ink">{step.label}</p>
              <p className="mt-1 text-xs leading-5 text-ink-secondary">{step.description}</p>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

interface CoachReportLoadingDialogProps {
  open: boolean
}

function CoachReportLoadingDialog({ open }: CoachReportLoadingDialogProps) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!open) return

    const start = performance.now()
    const updateElapsed = () => setElapsed((performance.now() - start) / 1000)
    const resetId = window.setTimeout(updateElapsed, 0)
    const id = window.setInterval(() => {
      updateElapsed()
    }, 250)
    return () => {
      window.clearTimeout(resetId)
      window.clearInterval(id)
    }
  }, [open])

  const progress = computeReportProgress(elapsed)
  const activePhase = pickReportLoadingPhase(elapsed)
  const ActiveIcon = activePhase.icon
  const percent = Math.round(progress * 100)

  return (
    <Dialog open={open}>
      <DialogContent
        className="sm:max-w-xl"
        onInteractOutside={(event) => event.preventDefault()}
        onEscapeKeyDown={(event) => event.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>Generando reporte con comparables reales</DialogTitle>
          <DialogDescription>
            Estamos preparando los comparables y el informe. Aparecerá automáticamente cuando termine.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-lg py-sm" role="status" aria-live="polite" aria-busy={open}>
          <div className="flex flex-col items-center gap-sm text-center">
            <div className="relative">
              <div className="absolute inset-0 animate-ping rounded-full bg-primary/20" />
              <div className="relative flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
                <Loader2 className="h-7 w-7 animate-spin text-primary" />
              </div>
            </div>
            <p
              key={activePhase.key}
              className="flex items-center gap-xs text-sm font-semibold text-ink animate-chat-bubble-in"
            >
              <ActiveIcon className="h-4 w-4 text-primary" />
              {activePhase.label}
            </p>
            <p className="max-w-md text-sm text-ink-secondary">{activePhase.detail}</p>
          </div>

          <div>
            <div
              className="relative h-2.5 w-full overflow-hidden rounded-pill bg-primary/10"
              role="progressbar"
              aria-valuenow={percent}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className="absolute inset-y-0 left-0 rounded-pill bg-primary transition-[width] duration-500 ease-out"
                style={{ width: `${percent}%` }}
              />
            </div>
            <div className="mt-xs flex items-center justify-between text-xs text-ink-muted">
              <span>{Math.floor(elapsed)}s transcurridos</span>
              <span>{percent}%</span>
            </div>
          </div>

          <div className="grid gap-xs">
            {REPORT_LOADING_PHASES.map((phase) => {
              const PhaseIcon = phase.icon
              const isActive = phase.key === activePhase.key
              const isDone = elapsed >= phase.from && !isActive
              return (
                <div
                  key={phase.key}
                  className={`flex items-center gap-sm rounded-xl border px-sm py-xs text-xs transition ${
                    isActive
                      ? 'border-primary/40 bg-primary/5 text-ink'
                      : isDone
                        ? 'border-emerald-200 bg-emerald-50/50 text-ink-secondary'
                        : 'border-line bg-surface text-ink-muted'
                  }`}
                >
                  <PhaseIcon className={`h-3.5 w-3.5 ${isActive ? 'text-primary' : ''}`} />
                  <span className="font-medium">{phase.label}</span>
                </div>
              )
            })}
          </div>

          <p className="text-center text-xs text-ink-muted">
            Puedes dejar esta ventana abierta. El reporte aparecerá automáticamente cuando termine.
          </p>
          {elapsed >= REPORT_LONG_RUNNING_HINT_AFTER_S && (
            <p className="rounded-xl border border-primary/20 bg-primary/5 px-md py-sm text-center text-xs text-ink-secondary">
              Sigue trabajando. Algunos anuncios requieren más tiempo por CAPTCHA o por la carga de detalle de la ficha.
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

interface CoachClientReportComposerProps {
  transaction: TransactionDetail
  valuationResult: CoachTransactionValuationResponse
}

interface EditableReportSection {
  id: string
  title: string
  body: string
}

function CoachClientReportComposer({
  transaction,
  valuationResult,
}: CoachClientReportComposerProps) {
  const { t } = useTranslation()
  const stats = valuationResult.valuation.stats
  const appreciation = valuationResult.valuation.market_appreciation ?? null
  const invested = totalSpent(transaction)

  // Mirror the investor-report recommended band so the email matches the
  // range the coach just validated on screen.
  const recommendedAnchor = stats.estimated_value ?? null
  const recommendedBand = priceBand(recommendedAnchor, 0.03)
  const recommendedGainLow = capitalGain(recommendedBand.low, invested)
  const recommendedGainHigh = capitalGain(recommendedBand.high, invested)
  const recommendedRoiLow = roiPercent(recommendedGainLow, invested)
  const recommendedRoiHigh = roiPercent(recommendedGainHigh, invested)
  const emailRoiText =
    recommendedRoiLow !== null && recommendedRoiHigh !== null
      ? ` — un ROI de entre ${formatEmailPercent(recommendedRoiLow)} y ${formatEmailPercent(recommendedRoiHigh)}`
      : ''
  const defaultTo = transaction.client_email ?? ''
  const area = coachEmailArea(transaction, valuationResult)
  const zoneName = appreciation?.town_name ?? valuationResult.valuation.municipio.name
  const subjectGain = formatSubjectGain(recommendedGainLow)
  const firstName = clientFirstName(transaction.transaction_name)
  const defaultSubject = subjectGain
    ? `${firstName}, tu propiedad en ${area} podría haber ganado más de ${subjectGain}`
    : `${firstName}, tu propiedad en ${area} podría haber ganado valor`
  const purchasePeriodText = appreciation ? ` en ${formatPeriod(appreciation.from_period)}` : ''
  const fromPeriod = appreciation ? formatPeriod(appreciation.from_period) : 'la compra'
  const toPeriod = appreciation ? formatPeriod(appreciation.to_period) : 'hoy'
  const initialSections: EditableReportSection[] = [
    {
      id: 'gain',
      title: 'Cómo lo calculamos',
      body: [
        `Tomamos la evolución del precio por m² en ${zoneName} (${fromPeriod} → ${toPeriod}), los datos de tu operación en ${valuationResult.valuation_request.address}, y el rango de salida que observamos hoy.`,
        'La fuente es TF Labs, basada en cierres trimestrales de registradores. No es una tasación oficial, pero sí una señal sólida de que puede ser buen momento para valorar una desinversión.',
      ].join('\n'),
    },
    {
      id: 'meaning',
      title: 'Qué significaría para ti',
      body: [
        'Capturar parte de esa plusvalía ahora te permitiría reinvertir con una estrategia más clara y más capital.',
        'El valor final dependerá de demanda real, estado del activo, fiscalidad y negociación — de todo eso hablamos contigo en detalle.',
      ].join('\n'),
    },
    {
      id: 'next-step',
      title: '¿Tiene sentido explorarlo?',
      body: [
        'Agenda una llamada gratuita con nuestros especialistas:',
        '👉 https://prophero.com/contacto',
        'En 30 minutos te ayudamos a aterrizar precio de salida, margen de negociación, timing, costes e impuestos.',
      ].join('\n'),
    },
  ]
  const emailIntroParagraphs = [
    'Desde PropHero monitorizamos continuamente el mercado para avisarte cuando aparece una oportunidad clara. Y hoy la vemos en tu propiedad.',
    `El €/m² en tu zona ha subido desde que compraste${purchasePeriodText}.`,
    recommendedGainLow !== null && recommendedGainHigh !== null
      ? `Según nuestra estimación, la ganancia potencial estaría entre ${formatEmailCurrencyRange(recommendedGainLow, recommendedGainHigh)}${emailRoiText}.`
      : `Según nuestra estimación, el rango de salida estaría entre ${formatCurrencyRange(recommendedBand.low, recommendedBand.high)}.`,
    'Te adjuntamos el informe completo, pero aquí tienes el resumen:',
  ]

  const [to, setTo] = useState(defaultTo)
  const [subject, setSubject] = useState(defaultSubject)
  const [mode, setMode] = useState<'preview' | 'edit'>('preview')
  const [sections, setSections] = useState<EditableReportSection[]>(initialSections)
  const [sending, setSending] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const emailBody = [
    `Hola ${firstName},`,
    '',
    ...emailIntroParagraphs.flatMap((paragraph) => [paragraph, '']),
    ...sections.flatMap((section) => [section.title, section.body, '']),
    'Un saludo,',
    'El equipo de PropHero',
  ].join('\n')

  function updateSection(sectionId: string, key: 'title' | 'body', value: string) {
    setSections((current) =>
      current.map((section) =>
        section.id === sectionId ? { ...section, [key]: value } : section,
      ),
    )
  }

  async function handleSend() {
    if (sending || !to.trim() || !subject.trim() || sections.every((section) => !section.body.trim())) return
    setSending(true)
    setMessage(null)
    setError(null)
    try {
      const response = await sendTransactionEmail(transaction.id, {
        to: to.trim(),
        subject: subject.trim(),
        body: emailBody.trim(),
        valuation_request: valuationResult.valuation_request,
        valuation: valuationResult.valuation,
        transaction,
        include_comparables: true,
      })
      setMessage(response.message)
    } catch (err) {
      const msg =
        err instanceof CoachApiError ? err.detail ?? err.message : (err as Error).message
      setError(msg || t('coach.email.unknownError'))
    } finally {
      setSending(false)
    }
  }

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-col gap-md border-b border-line bg-surface-muted p-lg md:flex-row md:items-start md:justify-between md:p-xl">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-primary">
            Informe para cliente
          </p>
          <h3 className="mt-1 text-xl font-semibold text-ink">Editar, revisar y enviar</h3>
          <p className="mt-1 max-w-2xl text-sm text-ink-secondary">
            Ajusta el relato antes de enviarlo: el coach controla el mensaje final, no sólo el dato.
          </p>
        </div>
        <div className="flex rounded-xl border border-line bg-white p-1 shadow-sm">
          <button
            type="button"
            onClick={() => setMode('preview')}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
              mode === 'preview' ? 'bg-primary text-white' : 'text-ink-secondary hover:text-ink'
            }`}
          >
            Vista previa
          </button>
          <button
            type="button"
            onClick={() => setMode('edit')}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
              mode === 'edit' ? 'bg-primary text-white' : 'text-ink-secondary hover:text-ink'
            }`}
          >
            Editar
          </button>
        </div>
      </div>

      <div className="grid gap-lg p-lg md:p-xl">
        <div className="grid gap-md md:grid-cols-2">
          <label className="grid gap-2 text-sm font-medium text-ink">
            {t('coach.email.to')}
            <Input value={to} onChange={(event) => setTo(event.target.value)} />
          </label>
          <label className="grid gap-2 text-sm font-medium text-ink">
            {t('coach.email.subject')}
            <Input value={subject} onChange={(event) => setSubject(event.target.value)} />
          </label>
        </div>

        <CoachReportPdfPreview
          valuationResult={valuationResult}
          variant="composer"
        />

        {mode === 'preview' ? (
          <div className="rounded-2xl border border-line bg-white p-lg shadow-sm">
            <div className="border-b border-line pb-md">
              <p className="text-sm text-ink-secondary">Para: {to || '—'}</p>
              <h4 className="mt-1 text-xl font-semibold text-ink">{subject}</h4>
              <p className="mt-1 text-sm text-ink-secondary">
                {valuationResult.valuation_request.address}
              </p>
            </div>
            <div className="mt-lg grid gap-lg">
              <div className="grid gap-3 text-sm leading-6 text-ink-secondary">
                <p>Hola {firstName},</p>
                {emailIntroParagraphs.map((paragraph) => (
                  <p key={paragraph}>{paragraph}</p>
                ))}
              </div>
              {sections.map((section) => (
                <section key={section.id}>
                  <h5 className="text-sm font-semibold uppercase tracking-wide text-primary">
                    {section.title}
                  </h5>
                  <p className="mt-2 whitespace-pre-line text-sm leading-6 text-ink-secondary">
                    {section.body}
                  </p>
                </section>
              ))}
            </div>
          </div>
        ) : (
          <div className="grid gap-md">
            {sections.map((section) => (
              <div key={section.id} className="rounded-2xl border border-line bg-surface p-md">
                <Input
                  value={section.title}
                  onChange={(event) => updateSection(section.id, 'title', event.target.value)}
                  className="font-semibold"
                />
                <textarea
                  value={section.body}
                  onChange={(event) => updateSection(section.id, 'body', event.target.value)}
                  rows={5}
                  className="mt-3 min-h-32 w-full rounded-md border border-input bg-white px-3 py-2 text-sm text-ink shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {message && (
        <div className="mx-lg mb-md rounded-xl border border-emerald-200 bg-emerald-50 px-md py-sm text-sm text-emerald-800 md:mx-xl">
          {message}
        </div>
      )}
      {error && (
        <div
          role="alert"
          className="mx-lg mb-md rounded-xl border border-destructive/30 bg-destructive/5 px-md py-sm text-sm text-destructive md:mx-xl"
        >
          {error}
        </div>
      )}

      <div className="flex flex-col gap-sm border-t border-line bg-surface-muted p-lg md:flex-row md:items-center md:justify-between md:p-xl">
        <p className="text-sm text-ink-secondary">
          Revisa la vista previa antes de enviarlo. El email incluirá todas las secciones editadas.
        </p>
        <Button
          type="button"
          size="lg"
          onClick={handleSend}
          disabled={sending || !to.trim() || !subject.trim() || sections.every((section) => !section.body.trim())}
          className="w-full rounded-xl shadow-card transition-shadow hover:shadow-lift sm:w-auto"
        >
          {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          {sending ? t('coach.email.sending') : 'Enviar al cliente'}
        </Button>
      </div>
    </Card>
  )
}

interface CoachInvestorReportProps {
  transaction: TransactionDetail
  valuationResult: CoachTransactionValuationResponse
}

function ComparableThumbnail({ listing }: { listing: CoachTransactionValuationResponse['valuation']['listings'][number] }) {
  const [failed, setFailed] = useState(false)

  if (!listing.image_url || failed) {
    return (
      <div className="flex h-16 w-20 shrink-0 items-center justify-center rounded-xl bg-surface-muted px-2 text-center text-[10px] leading-tight text-ink-muted">
        Sin foto
      </div>
    )
  }

  return (
    <img
      src={listing.image_url}
      alt={listing.title}
      className="h-16 w-20 shrink-0 rounded-xl bg-surface-muted object-cover"
      loading="lazy"
      onError={() => setFailed(true)}
    />
  )
}

function CoachInvestorReport({ transaction, valuationResult }: CoachInvestorReportProps) {
  const valuation = valuationResult.valuation
  const stats = valuationResult.valuation.stats
  const appreciation = valuation.market_appreciation ?? null
  const listings = valuation.listings.slice(0, 5)
  const invested = totalSpent(transaction)
  const hasComparables = listings.length > 0
  const isNoScrape = valuation.search_metadata.strategy === 'no_scrape'
  const isMockComparables = valuation.search_metadata.strategy === 'coach_mock'

  // Anchor points come straight from the backend valuation stats. We
  // intentionally do NOT show these as punctual numbers anymore — coaches
  // requested ranges so the client doesn't read a calculator-precise figure
  // and treat it as a guaranteed asking price.
  const recommendedAnchor = stats.estimated_value ?? null
  // Keep the client-facing recommendation conservative: one source-backed
  // range around the valuation anchor, rounded to avoid false precision.
  const recommendedBand = priceBand(recommendedAnchor, 0.03)

  const purchasePpm2 =
    transaction.purchase_eur_per_m2 ?? pricePerM2(invested, valuationResult.valuation_request.m2)

  // €/m² zona hoy now comes from the TF Labs municipal price series when
  // available; comparables stay as a fallback so the report doesn't go blank
  // when the appreciation lookup fails to resolve a town.
  const currentPpm2 = appreciation
    ? Math.round(appreciation.to_eur_per_m2)
    : pricePerM2(recommendedAnchor, valuationResult.valuation_request.m2) ?? stats.avg_price_per_m2 ?? null
  const ppm2DeltaPct =
    purchasePpm2 && currentPpm2 ? ((currentPpm2 - purchasePpm2) / purchasePpm2) * 100 : null

  // Two distinct gain figures, per product spec:
  //   1) zonePlusvalia = real-market appreciation × invested (data: TF Labs CSV)
  //   2) recommended scenario gain = exit at recommended range vs invested
  const zonePlusvalia = appreciation && invested ? Math.round(invested * appreciation.pct_change) : null
  const recommendedGainLow = capitalGain(recommendedBand.low, invested)
  const recommendedGainHigh = capitalGain(recommendedBand.high, invested)
  const recommendedRoiLow = roiPercent(recommendedGainLow, invested)
  const recommendedRoiHigh = roiPercent(recommendedGainHigh, invested)
  const settlementDate = formatDate(transaction.real_settlement_date)
  const selectedAddress = valuationResult.valuation_request.selected_address
  const selectedUnit = valuationResult.valuation_request.selected_cadastral_unit
  const propertyAddress =
    selectedAddress?.label ?? valuationResult.valuation_request.address ?? transaction.address ?? '—'
  const propertyType = valuationResult.valuation_request.property_type ?? transaction.type ?? '—'
  const propertyCondition = valuationResult.valuation_request.property_condition
  const propertyTypeLabel = propertyCondition
    ? `${propertyType} · ${propertyCondition.replace(/_/g, ' ')}`
    : propertyType
  const mapLat = selectedAddress?.lat ?? valuation.municipio.lat
  const mapLon = selectedAddress?.lon ?? valuation.municipio.lon
  const mapPosition: [number, number] | null = mapLat != null && mapLon != null ? [mapLat, mapLon] : null
  const searchRadius = stageRadiusMeters(valuation.search_metadata.final_stage)
  const searchStage = searchStageLabel(valuation.search_metadata.final_stage)

  // Methodology blurb — we adapt the data-source label to whatever the
  // backend actually used so the report doesn't claim "comparables activos"
  // when we only have the TF Labs €/m² anchor.
  const methodologySource = isNoScrape
    ? 'TF Labs, serie municipal basada en cierres trimestrales de registradores, aplicada a la superficie del inmueble'
    : stats.estimation_method === 'ols_lstsq'
      ? 'regresión sobre comparables activos en Idealista (precio, m², habitaciones, baños)'
      : 'mediana €/m² de comparables activos en Idealista aplicada a la superficie del inmueble'

  const comparablesBadge = isNoScrape
    ? 'TF Labs zonal'
    : isMockComparables
      ? 'Mock test'
      : 'Live'

  const recommendedRoiDisplay =
    recommendedRoiLow === null || recommendedRoiHigh === null
      ? '—'
      : recommendedRoiLow === recommendedRoiHigh
        ? formatPercent(recommendedRoiLow)
        : `${formatPercent(recommendedRoiLow)} – ${formatPercent(recommendedRoiHigh)}`

  return (
    <Card className="overflow-hidden border-primary/20">
      <div className="bg-gradient-to-br from-primary/10 via-surface to-surface px-lg py-xl md:px-xl">
        <p className="text-xs font-semibold uppercase tracking-wide text-primary">
          Reporte inversor
        </p>
        <div className="mt-2 grid gap-lg md:grid-cols-[1.3fr_0.7fr] md:items-end">
          <div>
            <h3 className="text-2xl font-semibold tracking-tight text-ink">
              Estimación conservadora de salida
            </h3>
            <p className="mt-2 max-w-2xl text-sm text-ink-secondary">
              Este resumen muestra un único rango recomendado, la fuente del cálculo y
              la ganancia potencial frente a la compra. No estima tiempos de venta.
            </p>
          </div>
          <div className="rounded-2xl border border-primary/20 bg-white/80 p-md shadow-sm">
            <p className="text-xs uppercase tracking-wide text-ink-muted">Rango recomendado</p>
            <p className="mt-1 text-2xl font-semibold text-primary">
              {formatCurrencyRange(recommendedBand.low, recommendedBand.high)}
            </p>
            <p className="mt-1 text-xs text-ink-secondary">
              Estimación orientativa, no tasación oficial ni precio garantizado.
            </p>
            <p className="mt-1 text-[11px] text-ink-muted">
              Redondeado a €1.000 para evitar precisión falsa.
            </p>
          </div>
        </div>
      </div>

      <div className="border-t border-line/70 px-lg py-md md:px-xl">
        <p className="text-sm font-semibold text-ink">Datos de la propiedad</p>
        <div className="mt-md grid gap-md md:grid-cols-[1.3fr_0.7fr]">
          <div className="rounded-2xl border border-line bg-surface p-md">
            <p className="text-xs uppercase tracking-wide text-ink-muted">Dirección</p>
            <p className="mt-1 text-sm font-semibold leading-snug text-ink">{propertyAddress}</p>
          </div>
          <div className="rounded-2xl border border-line bg-surface p-md">
            <p className="text-xs uppercase tracking-wide text-ink-muted">Referencia catastral</p>
            <p className="mt-1 break-all font-mono text-sm font-semibold text-ink">
              {selectedUnit?.cadastral_reference ?? transaction.cadastral_reference ?? '—'}
            </p>
          </div>
        </div>
        <div className="mt-md grid gap-md sm:grid-cols-2 md:grid-cols-4">
          <Metric label="Tipo" value={propertyTypeLabel} />
          <Metric label="Habitaciones" value={formatNumber(valuationResult.valuation_request.bedrooms)} />
          <Metric label="Baños" value={formatNumber(valuationResult.valuation_request.bathrooms)} />
          <Metric label="Superficie" value={formatNumber(valuationResult.valuation_request.m2, ' m²')} />
        </div>
      </div>

      <div className="grid gap-md p-lg sm:grid-cols-2 md:grid-cols-5 md:p-xl">
        <Metric label="Fecha de compra" value={settlementDate} />
        <Metric label="Total pagado" value={formatCurrency(invested)} emphasis />
        <Metric label="€/m² compra" value={formatPricePerM2(purchasePpm2)} />
        <Metric
          label={appreciation ? `€/m² zona (${formatPeriod(appreciation.to_period)})` : '€/m² zona hoy'}
          value={
            <span>
              {formatPricePerM2(currentPpm2)} {ppm2DeltaPct !== null && `(${formatPercent(ppm2DeltaPct)})`}
            </span>
          }
        />
        <Metric
          label={appreciation ? 'Plusvalía de zona' : 'Ganancia (rango recomendado)'}
          value={
            appreciation ? (
              <span className={zonePlusvalia !== null && zonePlusvalia >= 0 ? 'text-emerald-700' : ''}>
                {formatCurrency(zonePlusvalia)} {appreciation && `(${formatPercent(appreciation.pct_change * 100)})`}
              </span>
            ) : (
              <span
                className={
                  recommendedGainLow !== null && recommendedGainLow >= 0 ? 'text-emerald-700' : ''
                }
              >
                {formatCurrencyRange(recommendedGainLow, recommendedGainHigh)}
              </span>
            )
          }
          emphasis
        />
      </div>

      {appreciation && (
        <div className="border-t border-line/70 px-lg py-md md:px-xl">
          <div className="rounded-2xl border border-emerald-200 bg-emerald-50/40 p-md">
            <div className="flex flex-col gap-1 md:flex-row md:items-baseline md:justify-between md:gap-md">
              <div>
                <p className="text-sm font-semibold text-ink">
                  Apreciación de zona desde la compra · {appreciation.town_name}
                </p>
                <p className="text-xs text-ink-secondary">
                  Mediana €/m² del municipio entre el mes de la firma ({formatPeriod(appreciation.from_period)})
                  y el último dato disponible ({formatPeriod(appreciation.to_period)}).
                </p>
              </div>
              <p className="text-2xl font-semibold text-emerald-700">
                {formatPercent(appreciation.pct_change * 100)}
              </p>
            </div>
            <div className="mt-md grid gap-md md:grid-cols-[1fr_240px] md:items-start">
              <div>
                <dl className="grid gap-md text-sm sm:grid-cols-2 md:grid-cols-5">
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-ink-muted">€/m² compra real</dt>
                    <dd className="text-sm font-semibold text-ink">
                      {formatPricePerM2(purchasePpm2)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-ink-muted">€/m² zona al firmar</dt>
                    <dd className="text-sm font-semibold text-ink">
                      {formatPricePerM2(Math.round(appreciation.from_eur_per_m2))}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-ink-muted">€/m² más reciente</dt>
                    <dd className="text-sm font-semibold text-ink">
                      {formatPricePerM2(Math.round(appreciation.to_eur_per_m2))}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-ink-muted">Período</dt>
                    <dd className="text-sm font-semibold text-ink">
                      {appreciation.months_elapsed} meses
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-ink-muted">Anualizado</dt>
                    <dd className="text-sm font-semibold text-ink">
                      {appreciation.annualized_pct_change !== null
                        ? formatPercent(appreciation.annualized_pct_change * 100)
                        : '—'}
                    </dd>
                  </div>
                </dl>
                {invested && zonePlusvalia !== null && (
                  <p className="mt-md text-sm text-ink-secondary">
                    Aplicado a la inversión de <strong className="text-ink">{formatCurrency(invested)}</strong>,
                    la apreciación de la zona equivale a <strong className="text-emerald-700">{formatCurrency(zonePlusvalia)}</strong>{' '}
                    de plusvalía teórica si la propiedad siguió la mediana del municipio.
                  </p>
                )}
              </div>
              {mapPosition && (
                <figure className="overflow-hidden rounded-xl border border-emerald-200 bg-white">
                  <div className="h-[180px] w-full">
                    <MapView propertyPosition={mapPosition} height="180px" zoom={14} />
                  </div>
                  <figcaption className="border-t border-emerald-200/70 bg-white px-3 py-2 text-[11px] uppercase tracking-wide text-ink-muted">
                    {appreciation.town_name}
                  </figcaption>
                </figure>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="border-t border-line/70 px-lg py-md md:px-xl">
        <div className="rounded-2xl border border-line bg-surface p-md">
          <p className="text-sm font-semibold text-ink">Rango recomendado conservador</p>
          <p className="mt-1 text-xs text-ink-secondary">
            Usamos una banda estrecha alrededor de la valoración base para no presentar alternativas
            comerciales que no estén respaldados por datos de mercado.
          </p>
          <dl className="mt-md grid gap-3 text-sm md:grid-cols-3">
            <div>
              <dt className="text-ink-muted">Rango de salida</dt>
              <dd className="mt-1 font-semibold text-ink">{formatCurrencyRange(recommendedBand.low, recommendedBand.high)}</dd>
            </div>
            <div>
              <dt className="text-ink-muted">Ganancia vs compra</dt>
              <dd className="mt-1 font-semibold text-ink">{formatCurrencyRange(recommendedGainLow, recommendedGainHigh)}</dd>
            </div>
            <div>
              <dt className="text-ink-muted">ROI estimado</dt>
              <dd className="mt-1 font-semibold text-ink">{recommendedRoiDisplay}</dd>
            </div>
          </dl>
        </div>
        <p className="mt-md text-[11px] leading-relaxed text-ink-muted">
          El rango está redondeado a €1.000 para evitar precisión falsa. No estimamos tiempo de venta:
          dependerá de demanda real, estado del activo, documentación, fiscalidad y negociación.
        </p>
      </div>

      <div className="border-t border-line/70 bg-surface-muted px-lg py-md md:px-xl">
        <p className="text-sm font-semibold text-ink">Lectura de mercado para el cliente</p>
        <p className="mt-1 text-sm text-ink-secondary">
          {appreciation && hasComparables
            ? `La zona de ${appreciation.town_name} ha apreciado un ${formatPercent(appreciation.pct_change * 100)} desde la firma. El rango recomendado (${formatCurrencyRange(recommendedBand.low, recommendedBand.high)}) se construye sobre comparables activos hoy y se presenta como una estimación conservadora.`
            : appreciation
              ? `La zona de ${appreciation.town_name} ha apreciado un ${formatPercent(appreciation.pct_change * 100)} desde la firma. Sin comparables individuales, anclamos el rango recomendado (${formatCurrencyRange(recommendedBand.low, recommendedBand.high)}) en TF Labs: datos municipales basados en cierres trimestrales de registradores. Al ser una referencia de municipio, la propiedad individual puede variar; por eso recomendamos revisarlo en una reunión con un tasador.`
              : hasComparables
                ? 'El rango recomendado se construye sobre los comparables activos en el municipio y se presenta como una estimación conservadora, no como precio garantizado.'
                : 'Sin comparables individuales, anclamos el rango recomendado en TF Labs: datos municipales basados en cierres trimestrales de registradores. Al ser una referencia de municipio, la propiedad individual puede variar; por eso recomendamos revisarlo en una reunión con un tasador.'}
        </p>
        <p className="mt-2 text-[11px] leading-relaxed text-ink-muted">
          Fuente del rango: {methodologySource}.
        </p>
      </div>

      {hasComparables && (
        <div className="border-t border-line/70 px-lg py-lg md:px-xl">
          <div className="flex items-baseline justify-between gap-md">
            <div>
              <p className="text-sm font-semibold text-ink">Comparables activos</p>
              <p className="text-xs text-ink-secondary">
                Qué está viendo el comprador en el mercado hoy.
              </p>
            </div>
            <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
              {comparablesBadge}
            </span>
          </div>
          <div className="mt-md overflow-hidden rounded-2xl border border-line">
            {listings.map((listing) => (
              <a
                key={listing.url}
                href={listing.url}
                target="_blank"
                rel="noopener noreferrer"
                className="group flex gap-md border-b border-line/70 p-md transition-colors last:border-b-0 hover:bg-surface-muted focus:bg-surface-muted focus:outline-none"
                title={listing.url}
              >
                <ComparableThumbnail listing={listing} />
                <div className="grid min-w-0 flex-1 grid-cols-[1fr_auto] gap-md">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-ink group-hover:text-primary group-hover:underline">
                      {listing.title}
                    </p>
                    {listing.address && (
                      <p className="mt-0.5 truncate text-xs text-ink-muted">{listing.address}</p>
                    )}
                    <p className="mt-1 text-xs text-ink-secondary">
                      {[formatNumber(listing.m2 ?? null, ' m²'), formatNumber(listing.bedrooms ?? null, ' hab.'), formatNumber(listing.bathrooms ?? null, ' baños')]
                        .filter((value) => value !== '—')
                        .join(' · ')}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="text-sm font-semibold text-ink">{formatCurrency(listing.price)}</p>
                    <p className="text-xs text-ink-muted">{formatPricePerM2(listing.price_per_m2)}</p>
                  </div>
                </div>
              </a>
            ))}
          </div>
        </div>
      )}

      {mapPosition && hasComparables && (
        <div className="border-t border-line/70 px-lg py-md md:px-xl">
          <div className="rounded-2xl border border-line bg-surface-muted p-md">
            <div className="flex flex-col gap-1 md:flex-row md:items-baseline md:justify-between">
              <div>
                <p className="text-sm font-semibold text-ink">Mapa y radio de comparables</p>
                <p className="text-xs text-ink-secondary">
                  Dirección valorada y radio usado para seleccionar comparables activos.
                </p>
              </div>
              <p className="text-sm font-semibold text-primary">
                {searchRadius}m · {searchStage}
              </p>
            </div>
            <div className="mt-md overflow-hidden rounded-2xl border border-line bg-white">
              <MapView
                propertyPosition={mapPosition}
                radiusMeters={searchRadius}
                height="260px"
              />
            </div>
          </div>
        </div>
      )}

      <div className="border-t border-line/70 bg-ink px-lg py-lg text-white md:px-xl">
        <div className="grid gap-md md:grid-cols-[1fr_auto] md:items-center">
          <div>
            <p className="text-lg font-semibold">
              ¿Quieres aterrizar estos números con un experto?
            </p>
            <p className="mt-1 max-w-2xl text-sm text-white/75">
              Agenda una llamada <strong className="text-white">gratuita</strong> con el
              equipo de PropHero para gestionar la desinversión, validar el precio de
              salida y construir un plan comercial concreto sobre esta propiedad.
            </p>
          </div>
          <a
            href="https://prophero.com/contacto"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center gap-2 rounded-2xl bg-white px-md py-sm text-sm font-semibold text-ink shadow-sm transition hover:bg-white/90"
          >
            <Phone className="h-4 w-4" aria-hidden="true" />
            Llamada gratuita con PropHero
          </a>
        </div>
      </div>
    </Card>
  )
}

interface CoachReportPdfPreviewProps {
  valuationResult: CoachTransactionValuationResponse
  variant: 'report' | 'composer'
}

// Renders "Ver PDF" / "Descargar PDF" actions for the report PDF that will be
// attached to the coach email. Reuses the /api/report/pdf/render endpoint via
// `createReportPdfObjectUrl` so the preview never re-runs the scraper — it
// just turns the in-memory valuation into a PDF.
function CoachReportPdfPreview({ valuationResult, variant }: CoachReportPdfPreviewProps) {
  const { t } = useTranslation()
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    return () => {
      if (pdfUrl) URL.revokeObjectURL(pdfUrl)
    }
  }, [pdfUrl])

  const payload: ReportPdfPayload = {
    request: valuationResult.valuation_request,
    valuation: valuationResult.valuation,
    transaction: valuationResult.transaction,
  }

  async function ensurePdfUrl(): Promise<string | null> {
    if (pdfUrl) return pdfUrl
    const url = await createReportPdfObjectUrl(payload)
    setPdfUrl(url)
    return url
  }

  async function handlePreview() {
    setPreviewing(true)
    setError(null)
    try {
      const url = await ensurePdfUrl()
      if (url) setPreviewOpen(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('results.cta.previewError'))
    } finally {
      setPreviewing(false)
    }
  }

  async function handleDownload() {
    setDownloading(true)
    setError(null)
    try {
      await downloadReportPdf(payload)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('results.cta.downloadError'))
    } finally {
      setDownloading(false)
    }
  }

  const isComposer = variant === 'composer'
  const title = isComposer
    ? t('coach.email.attachmentTitle')
    : t('coach.report.pdfTitle')
  const description = isComposer
    ? t('coach.email.attachmentDescription')
    : t('coach.report.pdfDescription')

  return (
    <div className="rounded-2xl border border-line bg-surface-muted p-md">
      <div className="flex flex-col gap-md md:flex-row md:items-start md:justify-between">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Paperclip className="h-4 w-4" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-ink">{title}</p>
            <p className="mt-1 text-xs text-ink-secondary">{description}</p>
            <p className="mt-1 text-xs font-mono text-ink-muted">
              prophero-valoracion.pdf
            </p>
          </div>
        </div>
        <div className="flex shrink-0 gap-sm">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handlePreview}
            disabled={previewing}
          >
            {previewing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Eye className="h-4 w-4" />
            )}
            {previewing ? t('results.cta.loadingPdf') : t('results.cta.previewPdf')}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleDownload}
            disabled={downloading}
          >
            {downloading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Download className="h-4 w-4" />
            )}
            {downloading ? t('results.cta.downloadingPdf') : t('results.cta.downloadPdf')}
          </Button>
        </div>
      </div>

      {error && (
        <p className="mt-sm text-sm text-destructive" role="alert">
          {error}
        </p>
      )}

      {previewOpen && pdfUrl && (
        <div className="mt-md overflow-hidden rounded-2xl border border-line bg-bg">
          <div className="flex items-center justify-between gap-sm border-b border-line bg-surface px-md py-sm">
            <p className="text-sm font-semibold text-ink">
              {t('results.cta.pdfPreviewTitle')}
            </p>
            <button
              type="button"
              className="inline-flex h-8 w-8 items-center justify-center rounded-full text-ink-secondary transition-colors hover:bg-bg hover:text-ink"
              onClick={() => setPreviewOpen(false)}
              aria-label={t('results.cta.closePdfPreview')}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <iframe
            title={t('results.cta.pdfPreviewTitle')}
            src={pdfUrl}
            className="h-[70vh] w-full bg-white"
          />
        </div>
      )}
    </div>
  )
}

interface MetricProps {
  label: string
  value: React.ReactNode
  emphasis?: boolean
}

function Metric({ label, value, emphasis }: MetricProps) {
  return (
    <div className="flex flex-col gap-1">
      <dt className="text-xs uppercase tracking-wide text-ink-muted">{label}</dt>
      <dd
        className={
          emphasis
            ? 'text-xl font-semibold text-primary'
            : 'text-lg font-semibold text-ink'
        }
      >
        {value}
      </dd>
    </div>
  )
}
