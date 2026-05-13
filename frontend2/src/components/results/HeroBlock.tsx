import { useTranslation } from 'react-i18next'
import { TrendingUp, Home, RotateCcw, Zap } from 'lucide-react'
import type { ValuationStats, SearchMetadata, MunicipioInfo } from '@/lib/types'
import { getConfidenceLevel } from '@/lib/results'
import { formatPrice, formatPricePerM2, formatNumber } from './shared/formatters'
import { Metric } from './shared/Metric'
import { ConfidenceBadge } from './shared/ConfidenceBadge'

interface HeroBlockProps {
  stats: ValuationStats
  municipio: MunicipioInfo
  searchMetadata: SearchMetadata
  m2: number
  onReset: () => void
}

export function HeroBlock({ stats, municipio, searchMetadata, m2, onReset }: HeroBlockProps) {
  const { t } = useTranslation()
  const hasEstimate = stats.estimated_value != null
  const confidence = getConfidenceLevel(searchMetadata.final_stage, stats.total_comparables)

  return (
    <div className="rounded-card border border-line-subtle bg-surface-tint p-lg shadow-card md:p-xl">
      <div className="flex flex-wrap items-start justify-between gap-md">
        <div>
          <p className="text-text-sm font-medium uppercase tracking-wide text-ink-secondary">
            {t('results.estimatedValuation')}
          </p>
          <p className="mt-xs text-text-sm text-ink-muted">{municipio.name}</p>
        </div>
        <div className="flex items-center gap-sm">
          <ConfidenceBadge level={confidence} />
          <button type="button" onClick={onReset} className="btn-ghost">
            <RotateCcw className="h-3.5 w-3.5" />
            {t('results.newValuation')}
          </button>
        </div>
      </div>

      <div className="mt-md flex flex-col gap-sm">
        {hasEstimate ? (
          <>
            <p className="text-header-2xl font-semibold tracking-tight text-ink md:text-header-3xl">
              {formatPrice(stats.estimated_value)}
            </p>
            {stats.price_range_low != null && stats.price_range_high != null && (
              <p className="text-text-md text-ink-secondary">
                {t('results.range', { low: formatPrice(stats.price_range_low), high: formatPrice(stats.price_range_high) })}
              </p>
            )}
            {stats.avg_price_per_m2 != null && (
              <p className="font-mono text-text-sm text-ink-muted">
                {t('results.hero.breakdown', { m2, pricePerM2: formatNumber(stats.avg_price_per_m2) })}
              </p>
            )}
          </>
        ) : (
          <p className="text-text-lg text-ink-secondary">{t('results.noData')}</p>
        )}
      </div>

      <div className="mt-lg flex flex-wrap items-end justify-between gap-md">
        <div className="inline-flex items-center gap-xs rounded-pill bg-primary/10 px-md py-xs text-text-sm font-medium text-brand">
          <Zap className="h-3.5 w-3.5" />
          {t('results.hero.analyzedIn', {
            seconds: (searchMetadata.total_duration_ms / 1000).toFixed(1),
            count: stats.total_comparables,
          })}
        </div>

        <div className="flex flex-wrap gap-md">
          <Metric
            icon={<TrendingUp className="h-4 w-4 text-brand" />}
            label={t('results.avgPrice')}
            value={formatPrice(stats.avg_price)}
          />
          <Metric
            icon={<Home className="h-4 w-4 text-brand" />}
            label={t('results.avgPricePerM2')}
            value={formatPricePerM2(stats.avg_price_per_m2)}
          />
          <Metric
            icon={<Home className="h-4 w-4 text-ink-muted" />}
            label={t('results.comparables')}
            value={String(stats.total_comparables)}
          />
        </div>
      </div>
    </div>
  )
}
