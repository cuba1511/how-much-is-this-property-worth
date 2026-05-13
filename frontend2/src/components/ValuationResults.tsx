import { useTranslation } from 'react-i18next'
import { TrendingUp, Home, ExternalLink, RotateCcw } from 'lucide-react'
import type { ValuationResponse } from '@/lib/types'

interface ValuationResultsProps {
  result: ValuationResponse
  onReset: () => void
}

function formatPrice(value: number | null | undefined): string {
  if (value == null) return '—'
  return new Intl.NumberFormat('es-ES', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(value)
}

function formatPricePerM2(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0 }).format(value)} €/m²`
}

export function ValuationResults({ result, onReset }: ValuationResultsProps) {
  const { t } = useTranslation()
  const { stats, listings, municipio } = result
  const hasEstimate = stats.estimated_value != null

  return (
    <div className="flex flex-col gap-xl">
      {/* Valuation summary card */}
      <div className="rounded-2xl bg-surface-tint border border-line p-lg shadow-card">
        <div className="flex items-start justify-between gap-md flex-wrap">
          <div>
            <p className="text-sm font-medium text-ink-secondary uppercase tracking-wide">
              {t('results.estimatedValuation')}
            </p>
            <p className="text-ink-muted text-xs mt-1">{municipio.name}</p>
          </div>
          <button
            type="button"
            onClick={onReset}
            className="btn-ghost text-xs"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            {t('results.newValuation')}
          </button>
        </div>

        <div className="mt-md flex flex-wrap gap-lg items-end">
          {hasEstimate ? (
            <div>
              <p className="text-4xl font-bold text-ink tracking-tight">
                {formatPrice(stats.estimated_value)}
              </p>
              {stats.price_range_low != null && stats.price_range_high != null && (
                <p className="text-sm text-ink-secondary mt-1">
                  {t('results.range', { low: formatPrice(stats.price_range_low), high: formatPrice(stats.price_range_high) })}
                </p>
              )}
            </div>
          ) : (
            <p className="text-ink-secondary text-base">{t('results.noData')}</p>
          )}

          <div className="flex gap-md flex-wrap ml-auto">
            <Metric
              icon={<TrendingUp className="h-4 w-4 text-primary" />}
              label={t('results.avgPrice')}
              value={formatPrice(stats.avg_price)}
            />
            <Metric
              icon={<Home className="h-4 w-4 text-primary" />}
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

      {/* Listings */}
      {listings.length > 0 && (
        <div>
          <h2 className="text-base font-semibold text-ink mb-md">
            {t('results.comparablesFound', { count: listings.length })}
          </h2>
          <div className="grid grid-cols-1 gap-md sm:grid-cols-2 lg:grid-cols-3">
            {listings.map((listing, i) => (
              <a
                key={i}
                href={listing.url}
                target="_blank"
                rel="noopener noreferrer"
                className="group flex flex-col rounded-xl border border-line bg-surface shadow-card transition hover:shadow-lift hover:border-primary/30 overflow-hidden"
              >
                {listing.image_url && (
                  <div className="h-36 overflow-hidden bg-surface-muted">
                    <img
                      src={listing.image_url}
                      alt={listing.title}
                      className="h-full w-full object-cover transition group-hover:scale-105"
                      loading="lazy"
                    />
                  </div>
                )}
                <div className="flex flex-col gap-xs p-md flex-1">
                  <p className="text-sm font-semibold text-ink line-clamp-2 leading-snug">
                    {listing.title}
                  </p>
                  {listing.address && (
                    <p className="text-xs text-ink-muted line-clamp-1">{listing.address}</p>
                  )}
                  <div className="mt-auto pt-sm flex items-center justify-between gap-sm">
                    <div>
                      {listing.price != null && (
                        <p className="text-base font-bold text-ink">{formatPrice(listing.price)}</p>
                      )}
                      <div className="flex gap-sm flex-wrap">
                        {listing.m2 != null && (
                          <span className="text-xs text-ink-secondary">{t('results.m2', { count: listing.m2 })}</span>
                        )}
                        {listing.bedrooms != null && (
                          <span className="text-xs text-ink-secondary">{t('results.rooms', { count: listing.bedrooms })}</span>
                        )}
                        {listing.bathrooms != null && (
                          <span className="text-xs text-ink-secondary">{t('results.baths', { count: listing.bathrooms })}</span>
                        )}
                      </div>
                    </div>
                    <ExternalLink className="h-3.5 w-3.5 shrink-0 text-ink-muted group-hover:text-primary transition-colors" />
                  </div>
                </div>
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

interface MetricProps {
  icon: React.ReactNode
  label: string
  value: string
}

function Metric({ icon, label, value }: MetricProps) {
  return (
    <div className="flex flex-col gap-xs">
      <div className="flex items-center gap-xs text-xs text-ink-secondary">
        {icon}
        {label}
      </div>
      <p className="text-sm font-semibold text-ink">{value}</p>
    </div>
  )
}
