import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2 } from 'lucide-react'
import { AddressStep } from '@/components/steps/AddressStep'
import { UnitSelectionStep } from '@/components/steps/UnitSelectionStep'
import { lookupCadastralUnits } from '@/lib/api'
import type { CadastralUnit, ResolvedAddress } from '@/lib/types'

interface PropertyIdentificationStepProps {
  resolvedAddress: ResolvedAddress | null
  onResolvedAddress: (addr: ResolvedAddress | null) => void
  selectedUnit: CadastralUnit | null
  onSelectedUnit: (unit: CadastralUnit | null) => void
  onUnitsCountChange?: (count: number) => void
  submitting?: boolean
}

export function PropertyIdentificationStep({
  resolvedAddress,
  onResolvedAddress,
  selectedUnit,
  onSelectedUnit,
  onUnitsCountChange,
  submitting = false,
}: PropertyIdentificationStepProps) {
  const { t } = useTranslation()
  const [units, setUnits] = useState<CadastralUnit[]>([])
  const [loading, setLoading] = useState(false)
  const [lookupError, setLookupError] = useState<string | null>(null)
  const lastFetchedRef = useRef<string | null>(null)

  useEffect(() => {
    if (!resolvedAddress?.road || !resolvedAddress.house_number) {
      setUnits([])
      onSelectedUnit(null)
      onUnitsCountChange?.(0)
      lastFetchedRef.current = null
      return
    }

    const fetchKey = `${resolvedAddress.provider_id ?? resolvedAddress.label}`
    if (lastFetchedRef.current === fetchKey) return

    const controller = new AbortController()
    setLoading(true)
    setLookupError(null)
    onSelectedUnit(null)

    void lookupCadastralUnits(resolvedAddress, controller.signal)
      .then((response) => {
        lastFetchedRef.current = fetchKey
        setUnits(response.units)
        onUnitsCountChange?.(response.units.length)
        if (response.units.length === 1) {
          onSelectedUnit(response.units[0])
        }
      })
      .catch((err: Error) => {
        if (err.name === 'AbortError') return
        setUnits([])
        onUnitsCountChange?.(0)
        setLookupError(t('catastro.lookupError'))
      })
      .finally(() => setLoading(false))

    return () => controller.abort()
  }, [resolvedAddress, onSelectedUnit, t])

  const needsSelection = units.length > 1
  const singleUnit = units.length === 1

  return (
    <div className="flex flex-col gap-lg">
      <AddressStep
        resolvedAddress={resolvedAddress}
        onResolvedAddress={(addr) => {
          lastFetchedRef.current = null
          onResolvedAddress(addr)
        }}
        submitting={submitting}
      />

      {loading && (
        <div className="flex items-center gap-sm text-sm text-ink-secondary">
          <Loader2 className="h-4 w-4 animate-spin text-primary" />
          {t('catastro.loading')}
        </div>
      )}

      {lookupError && !loading && (
        <p className="rounded-xl border border-amber-200 bg-amber-50 px-md py-sm text-sm text-amber-900">
          {lookupError}
        </p>
      )}

      {!loading && !lookupError && units.length === 0 && resolvedAddress?.house_number && (
        <p className="rounded-xl border border-line bg-surface-tint px-md py-sm text-sm text-ink-secondary">
          {t('catastro.noUnits')}
        </p>
      )}

      {singleUnit && selectedUnit && !needsSelection && (
        <p className="rounded-xl border border-primary/20 bg-primary/5 px-md py-sm text-sm text-ink">
          {t('catastro.unitConfirmed', { label: selectedUnit.label })}
        </p>
      )}

      {needsSelection && resolvedAddress && (
        <UnitSelectionStep
          units={units}
          selected={selectedUnit}
          onSelect={onSelectedUnit}
          addressLabel={resolvedAddress.label}
          disabled={submitting}
        />
      )}
    </div>
  )
}
