import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Loader2, LogOut, Search, Send } from 'lucide-react'
import { Navbar } from '@/components/Navbar'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card } from '@/components/ui/card'
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

function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return new Intl.NumberFormat('es-ES', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(value)
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
  if (row.final_total_price === null && row.total_est_costs === null) return null
  return (row.final_total_price ?? 0) + (row.total_est_costs ?? 0)
}

function capitalGain(exitPrice: number | null | undefined, invested: number | null): number | null {
  if (exitPrice === null || exitPrice === undefined || invested === null) return null
  return exitPrice - invested
}

function roiPercent(gain: number | null, invested: number | null): number | null {
  if (gain === null || !invested) return null
  return (gain / invested) * 100
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
                      {t('coach.fields.finalTotalPrice')}
                    </span>
                    <span className="text-sm font-semibold text-ink">
                      {formatCurrency(row.final_total_price)}
                    </span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-xs uppercase tracking-wide text-ink-muted">
                      {t('coach.fields.totalEstCosts')}
                    </span>
                    <span className="text-sm font-semibold text-ink">
                      {formatCurrency(row.total_est_costs)}
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

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    setData(null)
    setValuationResult(null)
    setValuationError(null)
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

  const grandTotal = useMemo(() => {
    if (!data) return null
    const a = data.final_total_price ?? 0
    const b = data.total_est_costs ?? 0
    if (!data.final_total_price && !data.total_est_costs) return null
    return a + b
  }, [data])

  async function handleGenerateValuation() {
    if (valuationLoading) return
    setValuationLoading(true)
    setValuationError(null)
    try {
      const response = await generateTransactionValuation(transactionId)
      setValuationResult(response)
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

          <Card className="p-lg md:p-xl">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-secondary">
              {t('coach.detail.financialsTitle')}
            </h3>
            <dl className="mt-md grid grid-cols-1 gap-md md:grid-cols-3">
              <Metric
                label={t('coach.fields.finalTotalPrice')}
                value={formatCurrency(data.final_total_price)}
              />
              <Metric
                label={t('coach.fields.totalEstCosts')}
                value={formatCurrency(data.total_est_costs)}
              />
              <Metric
                label={t('coach.detail.totalSpent')}
                value={formatCurrency(grandTotal)}
                emphasis
              />
            </dl>
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

          <Card className="p-lg md:p-xl">
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
              onClick={handleGenerateValuation}
              disabled={valuationLoading}
            >
              {valuationLoading && <Loader2 className="h-4 w-4 animate-spin" />}
              {valuationLoading ? t('coach.valuation.generating') : t('coach.valuation.cta')}
            </Button>
          </Card>

          {valuationResult && (
            <>
              <CoachInvestorReport
                transaction={data}
                valuationResult={valuationResult}
              />
              <CoachClientReportComposer
                transaction={data}
                valuationResult={valuationResult}
              />
            </>
          )}
        </>
      )}
    </div>
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
  const market = valuationResult.valuation.market_transactions
  const avgDaysOnMarket = (() => {
    const days = market?.transactions
      .map((tx) => tx.days_on_market)
      .filter((value): value is number => value !== null && value !== undefined)
    if (!days?.length) return null
    return Math.round(days.reduce((sum, value) => sum + value, 0) / days.length)
  })()
  const invested = totalSpent(transaction)
  const recommended = stats.estimated_value ?? market?.summary.avg_closing_price ?? null
  const quickPrice = stats.price_range_low ?? (recommended ? Math.round(recommended * 0.94) : null)
  const aspirationalPrice = stats.price_range_high ?? (recommended ? Math.round(recommended * 1.04) : null)
  const gain = capitalGain(recommended, invested)
  const roi = roiPercent(gain, invested)
  const marketGap = market?.summary.asking_vs_closing_gap_pct ?? null
  const defaultTo = transaction.client_email ?? ''
  const defaultSubject = `Informe de performance PropHero — ${valuationResult.valuation_request.address}`
  const initialSections: EditableReportSection[] = [
    {
      id: 'summary',
      title: '1. Resumen ejecutivo',
      body: [
        `Hemos actualizado la lectura de mercado de ${valuationResult.valuation_request.address}.`,
        `El rango estimado de venta hoy está entre ${formatCurrency(quickPrice)} y ${formatCurrency(aspirationalPrice)}, con un precio recomendado de salida de ${formatCurrency(recommended)}.`,
        'Este rango busca equilibrar liquidez, negociación esperada y captura de plusvalía.',
      ].join('\n'),
    },
    {
      id: 'gain',
      title: '2. Capital gain estimado',
      body: [
        invested ? `Capital invertido aproximado: ${formatCurrency(invested)}.` : 'Capital invertido: pendiente de confirmar.',
        transaction.final_total_price ? `Precio de compra registrado: ${formatCurrency(transaction.final_total_price)}.` : null,
        transaction.total_est_costs ? `Costes adicionales estimados: ${formatCurrency(transaction.total_est_costs)}.` : null,
        gain !== null ? `Ganancia estimada al precio recomendado: ${formatCurrency(gain)} (${formatPercent(roi)}).` : 'Ganancia estimada: pendiente de confirmar.',
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
        marketGap !== null
          ? `Los cierres comparables muestran un descuento medio de ${formatPercent(-marketGap)} frente al precio anunciado.`
          : 'El mercado muestra margen de negociación entre precio anunciado y precio de cierre.',
        avgDaysOnMarket ? `El tiempo medio observado es de aproximadamente ${avgDaysOnMarket} días en mercado.` : null,
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
  const market = valuationResult.valuation.market_transactions
  const listings = valuation.listings.slice(0, 5)
  const closingRows = market?.transactions.slice(0, 5) ?? []
  const invested = totalSpent(transaction)
  const purchasePrice = transaction.final_total_price ?? null
  const investedCosts = transaction.total_est_costs ?? null
  const recommended = stats.estimated_value ?? market?.summary.avg_closing_price ?? null
  const quickPrice = stats.price_range_low ?? (recommended ? Math.round(recommended * 0.94) : null)
  const aspirationalPrice = stats.price_range_high ?? (recommended ? Math.round(recommended * 1.04) : null)
  const rangeGainLow = capitalGain(quickPrice, invested)
  const rangeGainHigh = capitalGain(aspirationalPrice, invested)
  const recommendedGain = capitalGain(recommended, invested)
  const recommendedRoi = roiPercent(recommendedGain, invested)
  const marketGap = market?.summary.asking_vs_closing_gap_pct ?? null
  const avgDaysOnMarket = (() => {
    const days = market?.transactions
      .map((tx) => tx.days_on_market)
      .filter((value): value is number => value !== null && value !== undefined)
    if (!days?.length) return null
    return Math.round(days.reduce((sum, value) => sum + value, 0) / days.length)
  })()

  const scenarios = [
    {
      label: 'Venta rápida',
      description: 'Precio para generar tracción y reducir tiempo en mercado.',
      price: quickPrice,
      gain: rangeGainLow,
      roi: roiPercent(rangeGainLow, invested),
      timing: '30–60 días',
    },
    {
      label: 'Recomendado',
      description: 'Balance entre capturar plusvalía y mantener una salida realista.',
      price: recommended,
      gain: recommendedGain,
      roi: recommendedRoi,
      timing: avgDaysOnMarket ? `${avgDaysOnMarket} días aprox.` : '60–90 días',
    },
    {
      label: 'Aspiracional',
      description: 'Para maximizar precio si el cliente puede esperar más.',
      price: aspirationalPrice,
      gain: rangeGainHigh,
      roi: roiPercent(rangeGainHigh, invested),
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
        <Metric label="Precio compra" value={formatCurrency(purchasePrice)} />
        <Metric label="Costes invertidos" value={formatCurrency(investedCosts)} />
        <Metric label="Capital invertido" value={formatCurrency(invested)} emphasis />
        <Metric
          label="Ganancia estimada"
          value={
            <span className={recommendedGain !== null && recommendedGain >= 0 ? 'text-emerald-700' : ''}>
              {formatCurrency(recommendedGain)} {recommendedRoi !== null && `(${formatPercent(recommendedRoi)})`}
            </span>
          }
          emphasis
        />
      </div>

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
                  <dt className="text-ink-muted">Capital gain</dt>
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
          En esta zona, los cierres reales del mock muestran un descuento medio de{' '}
          <strong className="text-ink">{formatPercent(marketGap ? -marketGap : null)}</strong>{' '}
          frente al precio anunciado
          {avgDaysOnMarket ? ` y un tiempo medio de ${avgDaysOnMarket} días en mercado` : ''}.
          La recomendación es salir con un precio que capture la plusvalía sin ignorar el margen
          de negociación que está aceptando el mercado.
        </p>
      </div>

      <div className="grid gap-md border-t border-line/70 px-lg py-lg md:grid-cols-2 md:px-xl">
        <div>
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
                  <p className="text-xs text-ink-muted">{formatCurrency(listing.price_per_m2)}/m²</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <p className="text-sm font-semibold text-ink">Cierres reales / referencia de salida</p>
          <p className="text-xs text-ink-secondary">
            Evidencia para explicar cuánto descuenta el comprador antes de cerrar.
          </p>
          <div className="mt-md overflow-hidden rounded-2xl border border-line">
            {closingRows.map((row) => (
              <div key={row.id} className="grid grid-cols-[1fr_auto] gap-md border-b border-line/70 p-md last:border-b-0">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-ink">{row.address ?? row.id}</p>
                  <p className="mt-1 text-xs text-ink-secondary">
                    {formatNumber(row.m2 ?? null, ' m²')} · {row.days_on_market ?? '—'} días mercado
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-semibold text-ink">{formatCurrency(row.closing_price)}</p>
                  <p className="text-xs text-ink-muted">
                    {formatPercent(row.negotiation_margin_pct ? -row.negotiation_margin_pct : null)} vs anunciado
                  </p>
                </div>
              </div>
            ))}
          </div>
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
