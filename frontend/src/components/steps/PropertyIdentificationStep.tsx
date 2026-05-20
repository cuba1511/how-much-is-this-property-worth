import { useCallback, useEffect, useRef, useState } from 'react'
import { useFormContext } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { FileSearch, Loader2, MapPin } from 'lucide-react'
import { AddressStep } from '@/components/steps/AddressStep'
import { UnitSelectionStep } from '@/components/steps/UnitSelectionStep'
import { CadastralReferenceSearch } from '@/components/CadastralReferenceSearch'
import { lookupCadastralUnits } from '@/lib/api'
import type { ValuationRequestForm } from '@/lib/schemas'
import type {
  CadastralUnit,
  IdentificationMode,
  ResolvedAddress,
} from '@/lib/types'

export type CatastroLookupStatus = 'idle' | 'loading' | 'done' | 'error'

interface PropertyIdentificationStepProps {
  resolvedAddress: ResolvedAddress | null
  onResolvedAddress: (addr: ResolvedAddress | null) => void
  selectedUnit: CadastralUnit | null
  onSelectedUnit: (unit: CadastralUnit | null) => void
  onUnitsCountChange?: (count: number) => void
  onLookupStatusChange?: (status: CatastroLookupStatus) => void
  submitting?: boolean
  /** Mode the user picked in the Hero. Defaults to 'address' for direct loads. */
  initialMode?: IdentificationMode
  /** Pre-fetched units when the Hero already resolved a cadastral reference.
   *  When non-empty, step 0 starts in 'done' state with these units listed
   *  and skips the Catastro-by-address effect on first mount. */
  initialUnits?: CadastralUnit[]
  /** Catastro-formatted label of the resolved reference; used as a fallback
   *  for the form's `address` field when geocoding failed. */
  initialReferenceLabel?: string | null
}

export function PropertyIdentificationStep({
  resolvedAddress,
  onResolvedAddress,
  selectedUnit,
  onSelectedUnit,
  onUnitsCountChange,
  onLookupStatusChange,
  submitting = false,
  initialMode = 'address',
  initialUnits = [],
  initialReferenceLabel = null,
}: PropertyIdentificationStepProps) {
  const { t } = useTranslation()
  const { setValue } = useFormContext<ValuationRequestForm>()
  const [mode, setMode] = useState<IdentificationMode>(initialMode)
  const [units, setUnits] = useState<CadastralUnit[]>(initialUnits)
  // If the Hero already pre-fetched a reference, treat step 0 as resolved on
  // mount and skip the address-mode effect via this ref.
  const seededFromReference =
    initialMode === 'reference' && initialUnits.length > 0
  const [lookupStatus, setLookupStatus] = useState<CatastroLookupStatus>(
    seededFromReference ? 'done' : 'idle',
  )
  const [lookupError, setLookupError] = useState<string | null>(null)
  const [referenceGeocodeWarning, setReferenceGeocodeWarning] = useState(
    seededFromReference && !resolvedAddress,
  )
  // Track whether we already consumed the initial seed. Once the user
  // interacts (switches tab, edits address, searches a new reference), this
  // flips and the address-mode effect runs normally again.
  const initialSeedConsumed = useRef(false)
  const lastFetchedRef = useRef<string | null>(null)

  // Mirror the seeded reference label into the form so step 0 validation
  // (which checks `address` is non-empty) passes without the user retyping
  // anything when they came from the Hero in reference mode.
  useEffect(() => {
    if (!seededFromReference) return
    const formAddress =
      resolvedAddress?.label ?? initialReferenceLabel ?? ''
    if (formAddress) {
      setValue('address', formAddress, { shouldValidate: true })
    }
    // Run once on mount; subsequent address changes go through their own paths.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Address mode: when we have a confirmed address with a portal, hit Catastro
  // to list units. Reference mode skips this — units come pre-populated from
  // the /api/catastro/by-reference call.
  useEffect(() => {
    if (mode !== 'address') return
    // Don't trample the seed coming from the Hero. The user has not interacted
    // yet, so the prefilled resolvedAddress from a previous reference resolve
    // would otherwise trigger a Catastro-by-address fetch we don't want.
    if (!initialSeedConsumed.current && seededFromReference) return
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
  }, [mode, resolvedAddress, onSelectedUnit, onUnitsCountChange, t])

  useEffect(() => {
    onLookupStatusChange?.(lookupStatus)
  }, [lookupStatus, onLookupStatusChange])

  const handleReferenceResolved = useCallback(
    (args: {
      resolvedAddress: ResolvedAddress | null
      units: CadastralUnit[]
      isParcel: boolean
      referenceLabel: string | null
    }) => {
      // User actively re-searched a reference: the Hero seed (if any) is now
      // stale and the address-mode effect can run normally again.
      initialSeedConsumed.current = true
      lastFetchedRef.current = null
      setReferenceGeocodeWarning(!args.resolvedAddress && args.units.length > 0)
      setLookupError(null)
      setUnits(args.units)
      setLookupStatus(args.units.length > 0 ? 'done' : 'error')
      onUnitsCountChange?.(args.units.length)
      onResolvedAddress(args.resolvedAddress)
      // Mirror the form field so step1Schema (which only checks `address`)
      // passes regardless of which input mode the user picked.
      const formAddress =
        args.resolvedAddress?.label ?? args.referenceLabel ?? ''
      setValue('address', formAddress, { shouldValidate: true })
      if (args.units.length === 1 && !args.isParcel) {
        onSelectedUnit(args.units[0])
      } else {
        onSelectedUnit(null)
      }
    },
    [onResolvedAddress, onSelectedUnit, onUnitsCountChange, setValue],
  )

  function handleModeChange(next: IdentificationMode) {
    if (next === mode) return
    // Reset state — switching mode invalidates whatever was selected before.
    initialSeedConsumed.current = true
    setMode(next)
    setUnits([])
    setLookupStatus('idle')
    setLookupError(null)
    setReferenceGeocodeWarning(false)
    lastFetchedRef.current = null
    onResolvedAddress(null)
    onSelectedUnit(null)
    onUnitsCountChange?.(0)
    setValue('address', '', { shouldValidate: false })
  }

  const needsSelection = lookupStatus === 'done' && units.length > 1
  const singleUnit = lookupStatus === 'done' && units.length === 1
  const showNoUnits =
    mode === 'address' &&
    lookupStatus === 'done' &&
    units.length === 0 &&
    Boolean(resolvedAddress?.house_number)

  return (
    <div className="flex flex-col gap-md">
      <div
        role="tablist"
        aria-label={t('catastro.tabs.address')}
        className="grid grid-cols-2 gap-2 rounded-2xl border border-line bg-surface-tint p-1"
      >
        <ModeTab
          active={mode === 'address'}
          onClick={() => handleModeChange('address')}
          icon={<MapPin className="h-4 w-4" />}
          label={t('catastro.tabs.address')}
          disabled={submitting}
        />
        <ModeTab
          active={mode === 'reference'}
          onClick={() => handleModeChange('reference')}
          icon={<FileSearch className="h-4 w-4" />}
          label={t('catastro.tabs.reference')}
          disabled={submitting}
        />
      </div>

      {mode === 'address' ? (
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
      ) : (
        <CadastralReferenceSearch
          onResolved={handleReferenceResolved}
          disabled={submitting}
        />
      )}

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

      {referenceGeocodeWarning && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-sm py-2 text-xs text-amber-900">
          {t('catastro.reference.geocodeWarning')}
        </p>
      )}

      {singleUnit && selectedUnit && (
        <p className="rounded-lg border border-primary/20 bg-primary/5 px-sm py-2 text-xs text-ink">
          {t('catastro.unitConfirmed', { label: selectedUnit.label })}
        </p>
      )}

      {needsSelection && (
        <UnitSelectionStep
          units={units}
          selected={selectedUnit}
          onSelect={onSelectedUnit}
          addressLabel={
            resolvedAddress?.label ?? t('catastro.tabs.reference')
          }
          disabled={submitting}
        />
      )}
    </div>
  )
}

interface ModeTabProps {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  label: string
  disabled?: boolean
}

function ModeTab({ active, onClick, icon, label, disabled }: ModeTabProps) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      disabled={disabled}
      className={`flex items-center justify-center gap-2 rounded-xl px-sm py-2 text-sm font-medium transition-all ${
        active
          ? 'bg-surface text-ink shadow-card border border-line'
          : 'text-ink-secondary hover:text-ink'
      } disabled:cursor-not-allowed disabled:opacity-50`}
    >
      {icon}
      {label}
    </button>
  )
}
