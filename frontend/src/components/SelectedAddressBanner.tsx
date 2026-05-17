import { MapPin } from 'lucide-react'
import type { CadastralUnit, ResolvedAddress } from '@/lib/types'
import { formatUnitSummary } from '@/lib/catastro-display'

interface SelectedAddressBannerProps {
  address: ResolvedAddress
  unit?: CadastralUnit | null
}

export function SelectedAddressBanner({ address, unit }: SelectedAddressBannerProps) {
  const unitLine = unit ? formatUnitSummary(unit) : null

  return (
    <div
      className="flex gap-sm rounded-lg border border-primary/15 bg-primary/5 px-sm py-2.5 text-sm text-ink"
      role="status"
    >
      <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
      <div className="min-w-0 flex-1 leading-snug">
        <p className="font-medium">{address.label}</p>
        {unitLine && (
          <p className="mt-0.5 text-xs text-ink-secondary">{unitLine}</p>
        )}
      </div>
    </div>
  )
}
