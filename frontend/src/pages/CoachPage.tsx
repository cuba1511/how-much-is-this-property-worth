import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  BarChart3,
  Building2,
  Calculator,
  CheckCircle2,
  FileText,
  Loader2,
  LogOut,
  MailCheck,
  MapPin,
  Search,
  Send,
  type LucideIcon,
} from 'lucide-react'
import { Navbar } from '@/components/Navbar'
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
  CoachTransactionValuationResponse,
  CoachApiError,
  TransactionDetail,
  TransactionSummary,
  clearStoredCoachPassword,
  generateTransactionValuation,
  getStoredCoachPassword,
  getTransaction,
  probeCoachPassword,
  sendTransactionEmail,
  searchTransactions,
  setStoredCoachPassword,
} from '@/lib/coach-api'

const SEARCH_DEBOUNCE_MS = 300
const REPORT_PROGRESS_CAP = 0.95
const REPORT_PROGRESS_TAU_SECONDS = 85
const REPORT_LONG_RUNNING_HINT_AFTER_S = 150

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
    from: 8,
    icon: Search,
    label: 'Buscando comparables reales',
    detail: 'Bright Data está abriendo Idealista y aplicando filtros de zona, m², habitaciones y baños.',
  },
  {
    key: 'enriching',
    from: 45,
    icon: Building2,
    label: 'Leyendo anuncios activos',
    detail: 'Revisamos los mejores comparables para extraer precio, superficie y características útiles.',
  },
  {
    key: 'pricing',
    from: 95,
    icon: BarChart3,
    label: 'Calculando rango de salida',
    detail: 'Combinamos comparables, €/m² y regresión para construir el precio recomendado.',
  },
  {
    key: 'reporting',
    from: 140,
    icon: Calculator,
    label: 'Armando reporte inversor',
    detail: 'Añadimos escenarios, plusvalía de zona y lectura de mercado para el coach.',
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

function totalSpent(row: TransactionSummary): number | null {
  return row.final_total_price ?? null
}

function pricePerM2(total: number | null | undefined, m2: number | null | undefined): number | null {
  if (!total || !m2) return null
  return Math.round(total / m2)
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

function clientName(transactionName: string): string {
  return transactionName.split(' - ')[0]?.trim() || transactionName
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

function TransactionSearchPanel({ onSelect, onUnauthorized }: TransactionSearchPanelProps) {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<TransactionSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Debounce + abort: cancel the previous in-flight request whenever the
  // query changes within SEARCH_DEBOUNCE_MS, so rapid typing never produces
  // a stale "first response wins" race.
  useEffect(() => {
    const controller = new AbortController()
    const handle = window.setTimeout(async () => {
      setLoading(true)
      setError(null)
      try {
        const rows = await searchTransactions(query, { signal: controller.signal })
        setResults(rows)
      } catch (err) {
        if ((err as Error).name === 'AbortError') return
        if (err instanceof CoachApiError && err.code === 'unauthorized') {
          onUnauthorized()
          return
        }
        const message =
          err instanceof CoachApiError ? err.message : (err as Error).message
        setError(message || t('coach.search.unknownError'))
      } finally {
        setLoading(false)
      }
    }, SEARCH_DEBOUNCE_MS)
    return () => {
      controller.abort()
      window.clearTimeout(handle)
    }
  }, [query, onUnauthorized, t])

  return (
    <div className="flex flex-col gap-md">
      <Card className="p-md">
        <div className="flex items-center gap-2 rounded-md border border-line bg-surface px-3 py-2">
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
      </Card>

      {error && (
        <div
          role="alert"
          className="rounded-xl border border-destructive/30 bg-destructive/5 px-md py-sm text-sm text-destructive"
        >
          {error}
        </div>
      )}

      <Card>
        <ul className="divide-y divide-line/60">
          {!loading && results.length === 0 && (
            <li className="px-lg py-2xl text-center text-sm text-ink-secondary">
              {query
                ? t('coach.search.noResults', { query })
                : t('coach.search.emptyState')}
            </li>
          )}
          {results.map((row) => (
            <li key={row.id}>
              <button
                type="button"
                onClick={() => onSelect(row.id)}
                className="flex w-full items-center justify-between gap-md px-lg py-md text-left transition hover:bg-surface-muted focus:bg-surface-muted focus:outline-none"
              >
                <div className="flex flex-col gap-0.5 min-w-0">
                  <span className="truncate text-sm font-semibold text-ink">
                    {row.transaction_name}
                  </span>
                  <span className="text-xs text-ink-secondary">
                    {[row.type, formatDate(row.created_at)].filter(Boolean).join(' · ') ||
                      '—'}
                  </span>
                </div>
                <div className="flex shrink-0 items-baseline gap-md text-right">
                  <div className="flex flex-col">
                    <span className="text-xs uppercase tracking-wide text-ink-muted">
                      {t('coach.detail.totalSpent')}
                    </span>
                    <span className="text-sm font-semibold text-primary">
                      {formatCurrency(totalSpent(row))}
                    </span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-xs uppercase tracking-wide text-ink-muted">
                      €/m² compra
                    </span>
                    <span className="text-sm font-semibold text-ink">
                      {formatPricePerM2(pricePerM2(totalSpent(row), row.landsize_m2))}
                    </span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-xs uppercase tracking-wide text-ink-muted">
                      {t('coach.fields.price')}
                    </span>
                    <span className="text-sm font-semibold text-ink">
                      {formatCurrency(row.price)}
                    </span>
                  </div>
                </div>
              </button>
            </li>
          ))}
        </ul>
      </Card>
    </div>
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
  const [reportView, setReportView] = useState<ReportFlowView>('setup')
  const generationRef = useRef<HTMLDivElement | null>(null)
  const reportRef = useRef<HTMLDivElement | null>(null)
  const composerRef = useRef<HTMLDivElement | null>(null)
  const reportVisible = Boolean(valuationResult) && reportView !== 'setup'
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
    if (reportVisible) {
      reportRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [reportVisible])

  useEffect(() => {
    if (composerUnlocked) {
      composerRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [composerUnlocked])

  const paidTotal = useMemo(() => {
    if (!data) return null
    return totalSpent(data)
  }, [data])

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
      const response = await generateTransactionValuation(transactionId)
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

          {reportVisible && valuationResult && (
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
              {!composerUnlocked && (
                <Card className="flex flex-col gap-md border-primary/20 bg-primary/5 p-lg md:flex-row md:items-center md:justify-between md:p-xl">
                  <div>
                    <p className="text-sm font-semibold text-ink">Reporte revisado</p>
                    <p className="mt-1 max-w-2xl text-sm text-ink-secondary">
                      Cuando el rango, la plusvalía y los comparables estén correctos, continúa al
                      editor del mensaje para preparar el envío al cliente.
                    </p>
                  </div>
                  <Button type="button" onClick={() => setReportView('composer')}>
                    Continuar a email
                    <Send className="h-4 w-4" />
                  </Button>
                </Card>
              )}
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
                    value={formatPricePerM2(pricePerM2(paidTotal, data.landsize_m2))}
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

              <Card className="p-lg md:p-xl">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-secondary">
                  {t('coach.detail.propertyTitle')}
                </h3>
                <dl className="mt-md grid grid-cols-2 gap-md md:grid-cols-4">
                  <Metric label={t('coach.fields.bedrooms')} value={formatNumber(data.bedrooms)} />
                  <Metric label={t('coach.fields.bathrooms')} value={formatNumber(data.bathrooms)} />
                  <Metric
                    label={t('coach.fields.landsize')}
                    value={formatNumber(data.landsize_m2, ' m²')}
                  />
                  <Metric label={t('coach.fields.type')} value={data.type ?? '—'} />
                </dl>
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
                <Button
                  type="button"
                  className="mt-md"
                  onClick={() => {
                    if (valuationResult) {
                      setReportView('report')
                      return
                    }
                    void handleGenerateValuation()
                  }}
                  disabled={valuationLoading}
                >
                  {valuationLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : valuationResult ? (
                    <FileText className="h-4 w-4" />
                  ) : null}
                  {valuationLoading
                    ? t('coach.valuation.generating')
                    : valuationResult
                      ? 'Ver reporte generado'
                      : t('coach.valuation.cta')}
                </Button>
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
      description: valuationLoading ? 'Calculando mercado y escenarios…' : 'Listo para lanzar la valoración.',
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
    if (!open) {
      setElapsed(0)
      return
    }

    const start = performance.now()
    const id = window.setInterval(() => {
      setElapsed((performance.now() - start) / 1000)
    }, 250)
    return () => window.clearInterval(id)
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
            Esto puede tardar un poco porque estamos usando Bright Data para leer Idealista en vivo.
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
              Sigue trabajando. Algunos anuncios requieren más tiempo por CAPTCHA, detalle de ficha o calentamiento
              de Bright Data.
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
  const recommended = stats.estimated_value ?? null
  const quickPrice = stats.price_range_low ?? (recommended ? Math.round(recommended * 0.94) : null)
  const aspirationalPrice = stats.price_range_high ?? (recommended ? Math.round(recommended * 1.04) : null)
  const purchasePpm2 = pricePerM2(invested, valuationResult.valuation_request.m2)
  const currentPpm2 = appreciation
    ? Math.round(appreciation.to_eur_per_m2)
    : pricePerM2(recommended, valuationResult.valuation_request.m2) ?? stats.avg_price_per_m2 ?? null
  const zonePlusvalia = appreciation && invested ? Math.round(invested * appreciation.pct_change) : null
  const recommendedGain = capitalGain(recommended, invested)
  const recommendedRoi = roiPercent(recommendedGain, invested)
  const defaultTo = transaction.client_email ?? ''
  const defaultSubject = `Informe de performance PropHero — ${valuationResult.valuation_request.address}`
  const initialSections: EditableReportSection[] = [
    {
      id: 'summary',
      title: '1. Resumen ejecutivo',
      body: [
        `Hemos actualizado la lectura de mercado de ${valuationResult.valuation_request.address}.`,
        `El rango estimado de venta hoy está entre ${formatCurrency(quickPrice)} y ${formatCurrency(aspirationalPrice)}, con un precio recomendado de salida de ${formatCurrency(recommended)}.`,
        purchasePpm2 && currentPpm2
          ? `Compró a ${formatPricePerM2(purchasePpm2)} y la zona hoy se mueve cerca de ${formatPricePerM2(currentPpm2)}.`
          : null,
        'Este rango busca equilibrar liquidez, negociación esperada y captura de plusvalía.',
      ].filter(Boolean).join('\n'),
    },
    {
      id: 'gain',
      title: '2. Plusvalía y ganancia estimada',
      body: [
        invested ? `Total pagado registrado en Airtable: ${formatCurrency(invested)}.` : 'Total pagado: pendiente de confirmar.',
        transaction.price ? `Precio base: ${formatCurrency(transaction.price)}.` : null,
        purchasePpm2 ? `€/m² de compra: ${formatPricePerM2(purchasePpm2)}.` : null,
        appreciation
          ? `€/m² mediano del municipio (${appreciation.town_name}) entre ${formatPeriod(appreciation.from_period)} y ${formatPeriod(appreciation.to_period)}: ${formatPricePerM2(Math.round(appreciation.from_eur_per_m2))} → ${formatPricePerM2(Math.round(appreciation.to_eur_per_m2))} (${formatPercent(appreciation.pct_change * 100)}${appreciation.annualized_pct_change !== null ? `, ${formatPercent(appreciation.annualized_pct_change * 100)} anualizado` : ''}).`
          : currentPpm2 ? `€/m² de mercado hoy: ${formatPricePerM2(currentPpm2)}.` : null,
        zonePlusvalia !== null
          ? `Plusvalía teórica si la propiedad siguió la mediana del municipio: ${formatCurrency(zonePlusvalia)}.`
          : null,
        recommendedGain !== null
          ? `Ganancia al precio recomendado de venta: ${formatCurrency(recommendedGain)} (${formatPercent(recommendedRoi)}).`
          : 'Ganancia al precio recomendado: pendiente de confirmar.',
      ].filter(Boolean).join('\n'),
    },
    {
      id: 'scenarios',
      title: '3. Escenarios de salida',
      body: [
        `Venta rápida: salir cerca de ${formatCurrency(quickPrice)} para generar tracción y reducir tiempo en mercado.`,
        `Escenario recomendado: salir cerca de ${formatCurrency(recommended)} para capturar plusvalía manteniendo una salida realista.`,
        `Escenario aspiracional: testar hasta ${formatCurrency(aspirationalPrice)} si no hay urgencia por vender.`,
      ].join('\n'),
    },
    {
      id: 'market',
      title: '4. Lectura de mercado',
      body: [
        appreciation
          ? `La zona de ${appreciation.town_name} ha apreciado un ${formatPercent(appreciation.pct_change * 100)} desde la firma (${formatPeriod(appreciation.from_period)} → ${formatPeriod(appreciation.to_period)}).`
          : null,
        'Los comparables activos en el municipio sostienen el rango propuesto.',
        'La recomendación es definir el precio de salida según prioridad: velocidad de venta o maximización de retorno.',
      ].filter(Boolean).join('\n'),
    },
    {
      id: 'next-step',
      title: '5. Siguiente paso',
      body: 'Si quieres, podemos revisar juntos los escenarios y definir una estrategia de salida concreta para decidir precio inicial, margen de negociación y timing.',
    },
  ]

  const [to, setTo] = useState(defaultTo)
  const [subject, setSubject] = useState(defaultSubject)
  const [mode, setMode] = useState<'preview' | 'edit'>('preview')
  const [sections, setSections] = useState<EditableReportSection[]>(initialSections)
  const [sending, setSending] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const emailBody = [
    `Hola ${clientName(transaction.transaction_name)},`,
    '',
    'Te comparto el informe actualizado de performance de tu propiedad:',
    '',
    ...sections.flatMap((section) => [section.title, section.body, '']),
    'Un saludo,',
    'PropHero',
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
          onClick={handleSend}
          disabled={sending || !to.trim() || !subject.trim() || sections.every((section) => !section.body.trim())}
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

function CoachInvestorReport({ transaction, valuationResult }: CoachInvestorReportProps) {
  const valuation = valuationResult.valuation
  const stats = valuationResult.valuation.stats
  const appreciation = valuation.market_appreciation ?? null
  const listings = valuation.listings.slice(0, 5)
  const invested = totalSpent(transaction)

  // Comparable-based exit range (still computed from listings — the user
  // explicitly asked to keep comparables and drop the closings mock).
  const recommended = stats.estimated_value ?? null
  const quickPrice = stats.price_range_low ?? (recommended ? Math.round(recommended * 0.94) : null)
  const aspirationalPrice = stats.price_range_high ?? (recommended ? Math.round(recommended * 1.04) : null)
  const purchasePpm2 = pricePerM2(invested, valuationResult.valuation_request.m2)

  // €/m² zona hoy now comes from the TF Labs municipal price series when
  // available; comparables stay as a fallback so the report doesn't go blank
  // when the appreciation lookup fails to resolve a town.
  const currentPpm2 = appreciation
    ? Math.round(appreciation.to_eur_per_m2)
    : pricePerM2(recommended, valuationResult.valuation_request.m2) ?? stats.avg_price_per_m2 ?? null
  const ppm2DeltaPct = appreciation
    ? appreciation.pct_change * 100
    : purchasePpm2 && currentPpm2 ? ((currentPpm2 - purchasePpm2) / purchasePpm2) * 100 : null

  // Two distinct gain figures, per product spec:
  //   1) zonePlusvalia = real-market appreciation × invested (data: TF Labs CSV)
  //   2) recommendedGain = exit at recommended price vs invested (data: comparables OLS)
  const zonePlusvalia = appreciation && invested ? Math.round(invested * appreciation.pct_change) : null
  const recommendedGain = capitalGain(recommended, invested)
  const recommendedRoi = roiPercent(recommendedGain, invested)

  const scenarios = [
    {
      label: 'Venta rápida',
      description: 'Precio para generar tracción y reducir tiempo en mercado.',
      price: quickPrice,
      gain: capitalGain(quickPrice, invested),
      roi: roiPercent(capitalGain(quickPrice, invested), invested),
      timing: '30–60 días',
    },
    {
      label: 'Recomendado',
      description: 'Balance entre capturar plusvalía y mantener una salida realista.',
      price: recommended,
      gain: recommendedGain,
      roi: recommendedRoi,
      timing: '60–90 días',
    },
    {
      label: 'Aspiracional',
      description: 'Para maximizar precio si el cliente puede esperar más.',
      price: aspirationalPrice,
      gain: capitalGain(aspirationalPrice, invested),
      roi: roiPercent(capitalGain(aspirationalPrice, invested), invested),
      timing: '90–150 días',
    },
  ]

  return (
    <Card className="overflow-hidden border-primary/20">
      <div className="bg-gradient-to-br from-primary/10 via-surface to-surface px-lg py-xl md:px-xl">
        <p className="text-xs font-semibold uppercase tracking-wide text-primary">
          Reporte inversor
        </p>
        <div className="mt-2 grid gap-lg md:grid-cols-[1.3fr_0.7fr] md:items-end">
          <div>
            <h3 className="text-2xl font-semibold tracking-tight text-ink">
              Cuánto ha ganado y cómo salir al mercado
            </h3>
            <p className="mt-2 max-w-2xl text-sm text-ink-secondary">
              Este resumen traduce la valoración en plusvalía, rango de salida y
              escenarios comerciales para que el cliente entienda el retorno de su inversión.
            </p>
          </div>
          <div className="rounded-2xl border border-primary/20 bg-white/80 p-md shadow-sm">
            <p className="text-xs uppercase tracking-wide text-ink-muted">Rango de venta hoy</p>
            <p className="mt-1 text-2xl font-semibold text-primary">
              {formatCurrency(quickPrice)} – {formatCurrency(aspirationalPrice)}
            </p>
            <p className="mt-1 text-xs text-ink-secondary">
              Precio recomendado: {formatCurrency(recommended)}
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-md p-lg md:grid-cols-4 md:p-xl">
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
          label={appreciation ? 'Plusvalía de zona' : 'Ganancia al precio recomendado'}
          value={
            appreciation ? (
              <span className={zonePlusvalia !== null && zonePlusvalia >= 0 ? 'text-emerald-700' : ''}>
                {formatCurrency(zonePlusvalia)} {appreciation && `(${formatPercent(appreciation.pct_change * 100)})`}
              </span>
            ) : (
              <span className={recommendedGain !== null && recommendedGain >= 0 ? 'text-emerald-700' : ''}>
                {formatCurrency(recommendedGain)} {recommendedRoi !== null && `(${formatPercent(recommendedRoi)})`}
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
            <dl className="mt-md grid gap-md text-sm md:grid-cols-4">
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-muted">€/m² al firmar</dt>
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
        </div>
      )}

      <div className="border-t border-line/70 px-lg py-md md:px-xl">
        <div className="grid gap-md md:grid-cols-3">
          {scenarios.map((scenario) => (
            <div key={scenario.label} className="rounded-2xl border border-line bg-surface p-md">
              <p className="text-sm font-semibold text-ink">{scenario.label}</p>
              <p className="mt-1 text-xs text-ink-secondary">{scenario.description}</p>
              <dl className="mt-md grid gap-2 text-sm">
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-muted">Precio salida</dt>
                  <dd className="font-semibold text-ink">{formatCurrency(scenario.price)}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-muted">Ganancia vs compra</dt>
                  <dd className="font-semibold text-ink">{formatCurrency(scenario.gain)}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-muted">ROI</dt>
                  <dd className="font-semibold text-ink">{formatPercent(scenario.roi)}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-muted">Tiempo venta</dt>
                  <dd className="font-semibold text-ink">{scenario.timing}</dd>
                </div>
              </dl>
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-line/70 bg-surface-muted px-lg py-md md:px-xl">
        <p className="text-sm font-semibold text-ink">Lectura de mercado para el cliente</p>
        <p className="mt-1 text-sm text-ink-secondary">
          {appreciation
            ? `La zona de ${appreciation.town_name} ha apreciado un ${formatPercent(appreciation.pct_change * 100)} desde la firma. La salida recomendada (${formatCurrency(recommended)}) se calcula sobre comparables activos y captura plusvalía sin alejarse del mercado actual.`
            : 'La salida recomendada se calcula sobre los comparables activos en el municipio. El rango entre venta rápida y aspiracional cubre los escenarios de liquidez vs maximización de retorno.'}
        </p>
      </div>

      <div className="border-t border-line/70 px-lg py-lg md:px-xl">
        <div className="flex items-baseline justify-between gap-md">
          <div>
            <p className="text-sm font-semibold text-ink">Comparables activos</p>
            <p className="text-xs text-ink-secondary">
              Qué está viendo el comprador en el mercado hoy.
            </p>
          </div>
          <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
            {valuation.search_metadata.strategy === 'coach_mock' ? 'Mock test' : 'Live'}
          </span>
        </div>
        <div className="mt-md overflow-hidden rounded-2xl border border-line">
          {listings.map((listing) => (
            <div key={listing.url} className="grid grid-cols-[1fr_auto] gap-md border-b border-line/70 p-md last:border-b-0">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-ink">{listing.title}</p>
                <p className="mt-1 text-xs text-ink-secondary">
                  {[formatNumber(listing.m2 ?? null, ' m²'), formatNumber(listing.bedrooms ?? null, ' hab.'), formatNumber(listing.bathrooms ?? null, ' baños')]
                    .filter((value) => value !== '—')
                    .join(' · ')}
                </p>
              </div>
              <div className="text-right">
                <p className="text-sm font-semibold text-ink">{formatCurrency(listing.price)}</p>
                <p className="text-xs text-ink-muted">{formatPricePerM2(listing.price_per_m2)}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-line/70 bg-ink px-lg py-lg text-white md:px-xl">
        <div className="grid gap-md md:grid-cols-[1fr_auto] md:items-center">
          <div>
            <p className="text-lg font-semibold">Siguiente paso recomendado</p>
            <p className="mt-1 max-w-2xl text-sm text-white/75">
              Usar este rango para llamar al cliente con una conversación simple:
              cuánto invirtió, cuánto ha ganado y qué precio conviene si quiere vender rápido
              versus maximizar retorno.
            </p>
          </div>
          <div className="rounded-2xl bg-white px-md py-sm text-sm font-semibold text-ink">
            Agendar llamada de salida
          </div>
        </div>
      </div>
    </Card>
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
