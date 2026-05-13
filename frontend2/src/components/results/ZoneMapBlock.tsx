import { useTranslation } from 'react-i18next'
import { MapView } from '@/components/MapView'
import type { MunicipioInfo, MarketTransaction, ResolvedAddress } from '@/lib/types'
import { stageRadiusMeters } from '@/lib/results'
import { formatPrice } from './shared/formatters'

interface ZoneMapBlockProps {
  municipio: MunicipioInfo
  selectedAddress?: ResolvedAddress | null
  transactions: MarketTransaction[]
  finalStage: string
}

export function ZoneMapBlock({ municipio, selectedAddress, transactions, finalStage }: ZoneMapBlockProps) {
  const { t } = useTranslation()

  const lat = selectedAddress?.lat ?? municipio.lat
  const lon = selectedAddress?.lon ?? municipio.lon
  if (lat == null || lon == null) return null

  const position: [number, number] = [lat, lon]
  const radius = stageRadiusMeters(finalStage)
  const sortedTx = [...transactions].sort((a, b) => (a.distance_m ?? Infinity) - (b.distance_m ?? Infinity))

  return (
    <div className="card-surface p-lg">
      <h2 className="text-header-sm mb-xs">{t('results.zone.title')}</h2>
      <p className="mb-md text-text-sm text-ink-muted">
        {t('results.zone.radiusHint', {
          radius,
          stage: t(`results.stages.${finalStage}`, { defaultValue: finalStage }),
        })}
      </p>

      <div className="overflow-hidden rounded-md border border-line-subtle">
        <MapView
          propertyPosition={position}
          radiusMeters={radius}
          height="280px"
        />
      </div>

      {sortedTx.length > 0 && (
        <div className="mt-md">
          <p className="mb-sm text-text-sm font-medium text-ink-secondary">{t('results.zone.nearbyTransactions')}</p>
          <div className="max-h-48 divide-y divide-line-subtle overflow-y-auto">
            {sortedTx.slice(0, 10).map((tx) => (
              <div key={tx.id} className="flex items-center justify-between py-sm text-text-sm">
                <div className="flex flex-col gap-0-5">
                  <span className="line-clamp-1 font-medium text-ink">{tx.address ?? '—'}</span>
                  {tx.distance_m != null && (
                    <span className="text-ink-muted">{tx.distance_m}m</span>
                  )}
                </div>
                <div className="ml-sm shrink-0 text-right">
                  {tx.closing_price != null ? (
                    <span className="font-semibold text-ink">{formatPrice(tx.closing_price)}</span>
                  ) : tx.asking_price != null ? (
                    <span className="text-ink-secondary">{formatPrice(tx.asking_price)}</span>
                  ) : (
                    <span className="text-ink-muted">—</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
