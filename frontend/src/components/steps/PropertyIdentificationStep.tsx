import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2 } from 'lucide-react'
import { AddressStep } from '@/components/steps/AddressStep'
import { UnitSelectionStep } from '@/components/steps/UnitSelectionStep'
import { lookupCadastralUnits } from '@/lib/api'
import type { CadastralUnit, ResolvedAddress } from '@/lib/types'

type LookupStatus = 'idle' | 'loading' | 'done' | 'error'

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
  const [lookupStatus, setLookupStatus] = useState<LookupStatus>('idle')
  const [lookupError, setLookupError] = useState<string | null>(null)
  const lastFetchedRef = useRef<string | null>(null)

  useEffect(() => {
    if (!resolvedAddress?.road || !resolvedAddress.house_number) {
      setUnits([])
      setLookupStatus('idle')
      setLookupError(null)
      onSelectedUnit(null)
      onUnitsCountChange?.(0)
      lastFetchedRef.current = null
      return
    }

    const fetchKey = `${resolvedAddress.provider_id ?? resolvedAddress.label}`
    if (lastFetchedRef.current === fetchKey) return

    const controller = new AbortController()
    setLookupStatus('loading')
    setLookupError(null)
    setUnits([])
    onSelectedUnit(null)
    onUnitsCountChange?.(0)

    void lookupCadastralUnits(resolvedAddress, controller.signal)
      .then((response) => {
        lastFetchedRef.current = fetchKey
        setUnits(response.units)
        setLookupStatus('done')
        onUnitsCountChange?.(response.units.length)
        if (response.units.length === 1) {
          onSelectedUnit(response.units[0])
        }
      })
      .catch((err: Error) => {
        if (err.name === 'AbortError') return
        setUnits([])
        setLookupStatus('error')
        onUnitsCountChange?.(0)
        setLookupError(t('catastro.lookupError'))
      })

    return () => controller.abort()
  }, [resolvedAddress, onSelectedUnit, onUnitsCountChange, t])

  const needsSelection = lookupStatus === 'done' && units.length > 1
  const singleUnit = lookupStatus === 'done' && units.length === 1
  const showNoUnits =
    lookupStatus === 'done' && units.length === 0 && Boolean(resolvedAddress?.house_number)

  return (
    <div className="flex flex-col gap-md">
      <AddressStep
        resolvedAddress={resolvedAddress}
        onResolvedAddress={(addr) => {
          lastFetchedRef.current = null
          setLookupStatus(addr?.house_number ? 'loading' : 'idle')
          setUnits([])
          setLookupError(null)
          onResolvedAddress(addr)
        }}
        submitting={submitting}
      />

      {lookupStatus === 'loading' && (
        <div className="flex items-center gap-sm rounded-lg border border-line bg-surface-tint px-sm py-2 text-xs text-ink-secondary">
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
          {t('catastro.loading')}
        </div>
      )}

      {lookupStatus === 'error' && lookupError && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-sm py-2 text-xs text-amber-900">
          {lookupError}
        </p>
      )}

      {showNoUnits && (
        <p className="rounded-lg border border-line bg-surface-tint px-sm py-2 text-xs text-ink-secondary">
          {t('catastro.noUnits')}
        </p>
      )}

      {singleUnit && selectedUnit && (
        <p className="rounded-lg border border-primary/20 bg-primary/5 px-sm py-2 text-xs text-ink">
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
