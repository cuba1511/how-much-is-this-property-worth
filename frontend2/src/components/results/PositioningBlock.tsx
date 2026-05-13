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
    <div className="rounded-2xl border border-line bg-surface p-lg shadow-card">
      <h2 className="text-base font-semibold text-ink mb-md">{t('results.positioning.title')}</h2>

      {bedroomAvg != null && (
        <div className="rounded-xl bg-surface-muted p-md mb-md">
          <p className="text-xs text-ink-secondary mb-1">
            {t('results.positioning.bedroomRefined', { count: bedrooms })}
          </p>
          <p className="text-2xl font-bold text-ink">{formatPricePerM2(bedroomAvg)}</p>
          {(() => {
            const delta = bedroomAvg - avgPricePerM2
            const sign = delta >= 0 ? '+' : ''
            return (
              <p className={`text-xs mt-1 ${delta >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                {sign}{formatPricePerM2(delta)} {t('results.positioning.vsGlobal')}
              </p>
            )
          })()}
        </div>
      )}

      {/* Spread bar */}
      <p className="text-xs font-medium text-ink-secondary mb-sm">{t('results.positioning.spread')}</p>
      <div className="relative h-8 rounded-full bg-gradient-to-r from-primary/10 via-primary/25 to-primary/10">
        <div
          className="absolute top-0 h-full w-1 bg-primary rounded-full"
          style={{ left: `${Math.min(Math.max(avgPosition, 2), 98)}%`, transform: 'translateX(-50%)' }}
        />
        <div className="absolute inset-x-0 top-full mt-1 flex justify-between text-[10px] text-ink-muted">
          <span>{t('results.positioning.min')}: {formatPricePerM2(min)}</span>
          <span>{t('results.positioning.avg')}: {formatPricePerM2(avgPricePerM2)}</span>
          <span>{t('results.positioning.max')}: {formatPricePerM2(max)}</span>
        </div>
      </div>
    </div>
  )
}
