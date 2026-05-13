import { useTranslation } from 'react-i18next'
import type { Listing } from '@/lib/types'
import { bedroomMatchedAvg } from '@/lib/results'
import { formatPricePerM2 } from './shared/formatters'

interface PositioningBlockProps {
  listings: Listing[]
  bedrooms: number
  m2: number
  avgPricePerM2: number
}

export function PositioningBlock({ listings, bedrooms, avgPricePerM2 }: PositioningBlockProps) {
  const { t } = useTranslation()

  const bedroomAvg = bedroomMatchedAvg(listings, bedrooms)

  const pricesPerM2 = listings
    .map((l) => l.price_per_m2)
    .filter((p): p is number => p != null)
    .sort((a, b) => a - b)

  if (pricesPerM2.length < 3) return null

  const min = pricesPerM2[0]
  const max = pricesPerM2[pricesPerM2.length - 1]
  const range = max - min
  const avgPosition = range > 0 ? ((avgPricePerM2 - min) / range) * 100 : 50

  return (
    <div className="card-surface p-lg">
      <h2 className="text-header-sm mb-md">{t('results.positioning.title')}</h2>

      {bedroomAvg != null && (
        <div className="mb-md rounded-md bg-surface-muted p-md">
          <p className="mb-xs text-text-sm text-ink-secondary">
            {t('results.positioning.bedroomRefined', { count: bedrooms })}
          </p>
          <p className="text-header-lg font-semibold text-ink">{formatPricePerM2(bedroomAvg)}</p>
          {(() => {
            const delta = bedroomAvg - avgPricePerM2
            const sign = delta >= 0 ? '+' : ''
            return (
              <p className={[
                'mt-xs text-text-sm font-medium',
                delta >= 0 ? 'text-success-fg' : 'text-destructive',
              ].join(' ')}>
                {sign}{formatPricePerM2(delta)} {t('results.positioning.vsGlobal')}
              </p>
            )
          })()}
        </div>
      )}

      {/* Spread bar */}
      <p className="mb-sm text-text-sm font-medium text-ink-secondary">{t('results.positioning.spread')}</p>
      <div className="relative h-8 rounded-pill bg-gradient-to-r from-primary/10 via-primary/25 to-primary/10">
        <div
          className="absolute top-0 h-full w-1 rounded-pill bg-primary"
          style={{ left: `${Math.min(Math.max(avgPosition, 2), 98)}%`, transform: 'translateX(-50%)' }}
        />
        <div className="absolute inset-x-0 top-full mt-xs flex justify-between text-text-xs text-ink-muted">
          <span>{t('results.positioning.min')}: {formatPricePerM2(min)}</span>
          <span>{t('results.positioning.avg')}: {formatPricePerM2(avgPricePerM2)}</span>
          <span>{t('results.positioning.max')}: {formatPricePerM2(max)}</span>
        </div>
      </div>
    </div>
  )
}
