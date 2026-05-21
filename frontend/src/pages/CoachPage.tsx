import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Loader2, LogOut, Search } from 'lucide-react'
import { Navbar } from '@/components/Navbar'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card } from '@/components/ui/card'
import {
  CoachApiError,
  TransactionDetail,
  TransactionSummary,
  clearStoredCoachPassword,
  getStoredCoachPassword,
  getTransaction,
  probeCoachPassword,
  searchTransactions,
  setStoredCoachPassword,
} from '@/lib/coach-api'

const SEARCH_DEBOUNCE_MS = 300

function formatCurrency(value: number | null): string {
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
          <div className="mx-auto w-full max-w-5xl">
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

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    setData(null)
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
              {t('coach.detail.nextStepTitle')}
            </h3>
            <p className="mt-2 text-sm text-ink-secondary">
              {t('coach.detail.nextStepDescription')}
            </p>
            <Button type="button" className="mt-md" disabled>
              {t('coach.detail.nextStepCta')}
            </Button>
          </Card>
        </>
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
