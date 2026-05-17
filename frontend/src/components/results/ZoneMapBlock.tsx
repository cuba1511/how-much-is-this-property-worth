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
    <div className="rounded-2xl border border-line bg-surface p-lg shadow-card">
      <h2 className="text-base font-semibold text-ink mb-xs">{t('results.zone.title')}</h2>
      <p className="text-xs text-ink-muted mb-md">
        {t('results.zone.radiusHint', {
          radius,
          stage: t(`results.stages.${finalStage}`, { defaultValue: finalStage }),
        })}
      </p>

      <div className="overflow-hidden rounded-2xl border border-line">
        <MapView
          propertyPosition={position}
          radiusMeters={radius}
          height="280px"
        />
      </div>

      {sortedTx.length > 0 && (
        <div className="mt-md">
          <p className="text-xs font-medium text-ink-secondary mb-sm">{t('results.zone.nearbyTransactions')}</p>
          <div className="max-h-48 overflow-y-auto divide-y divide-line">
            {sortedTx.slice(0, 10).map((tx) => (
              <div key={tx.id} className="flex items-center justify-between py-2 text-xs">
                <div className="flex flex-col gap-0.5">
                  <span className="text-ink font-medium line-clamp-1">{tx.address ?? '—'}</span>
                  {tx.distance_m != null && (
                    <span className="text-ink-muted">{tx.distance_m}m</span>
                  )}
                </div>
                <div className="text-right shrink-0 ml-sm">
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
