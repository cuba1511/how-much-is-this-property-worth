import { useCallback, useEffect, useRef, useState } from 'react'
import { useFormContext } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { FileSearch, Loader2, MapPin } from 'lucide-react'
import { AddressStep } from '@/components/steps/AddressStep'
import { UnitSelectionStep } from '@/components/steps/UnitSelectionStep'
import { CadastralReferenceSearch } from '@/components/CadastralReferenceSearch'
import {
  CatastroLookupTimeoutError,
  lookupCadastralUnits,
} from '@/lib/api'
import type { ValuationRequestForm } from '@/lib/schemas'
import type {
  CadastralUnit,
  IdentificationMode,
  ResolvedAddress,
} from '@/lib/types'

/** How long to wait before offering the user an explicit "Continuar sin
 *  Catastro" escape hatch. Lookup itself has a hard 20s timeout in
 *  `lookupCadastralUnits` — this surfaces an option earlier so users don't
 *  feel stuck staring at the spinner. */
const SKIP_OPTION_AFTER_MS = 6_000

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
  // Held outside React state so the "skip Catastro" button can abort the
  // in-flight upstream call without going through a re-render cycle.
  const fetchControllerRef = useRef<AbortController | null>(null)
  const [showSkipOption, setShowSkipOption] = useState(false)

  // Stash callbacks + t in refs so the lookup useEffect below can depend ONLY
  // on `mode` + `resolvedAddress`. Without this, an identity change in `t`
  // (e.g. when i18next swaps language or finishes loading a namespace) while
  // the Catastro fetch is in flight would:
  //   1) trigger the effect cleanup → `controller.abort()` kills the request
  //   2) re-run the effect → early-return on the `lastFetchedRef === fetchKey`
  //      dedup guard, so NO new fetch starts
  //   3) the aborted promise falls through `if (err.name === 'AbortError')`
  //      without touching state
  //   → `lookupStatus` stays at 'loading' forever ("Buscando inmuebles…"
  //   spinner that never resolves). Bug observed on /Calle de Ponciano 7.
  const tRef = useRef(t)
  tRef.current = t
  const onSelectedUnitRef = useRef(onSelectedUnit)
  onSelectedUnitRef.current = onSelectedUnit
  const onUnitsCountChangeRef = useRef(onUnitsCountChange)
  onUnitsCountChangeRef.current = onUnitsCountChange

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
      onSelectedUnitRef.current(null)
      onUnitsCountChangeRef.current?.(0)
      lastFetchedRef.current = null
      return
    }

    // Include house_number so `commitPortal` (suggestion without portal →
    // user types the portal → same provider_id) re-triggers the lookup
    // instead of being silently deduped against the no-portal attempt.
    const fetchKey = `${
      resolvedAddress.provider_id ?? resolvedAddress.label
    }|${resolvedAddress.house_number}`
    if (lastFetchedRef.current === fetchKey) return

    const controller = new AbortController()
    fetchControllerRef.current = controller
    // Mark the fetch as "in progress" *before* awaiting so a re-render
    // triggered by setLookupStatus('loading') doesn't slip past the
    // early-return guard above and spawn a duplicate fetch.
    lastFetchedRef.current = fetchKey
    setLookupStatus('loading')
    setLookupError(null)
    setUnits([])
    onSelectedUnitRef.current(null)
    onUnitsCountChangeRef.current?.(0)

    void lookupCadastralUnits(resolvedAddress, controller.signal)
      .then((response) => {
        setUnits(response.units)
        setLookupStatus('done')
        onUnitsCountChangeRef.current?.(response.units.length)
        if (response.units.length === 1) {
          onSelectedUnitRef.current(response.units[0])
        }
      })
      .catch((err: Error) => {
        // Caller-driven aborts (cleanup on unmount or address change) are
        // intentional: leave state alone so the next effect run takes over.
        if (err.name === 'AbortError') return
        // Hard timeout / network error / Catastro 4xx-5xx: allow the user to
        // proceed without the unit selector (it's an optional refinement, not
        // a required input).
        const isTimeout = err instanceof CatastroLookupTimeoutError
        setUnits([])
        setLookupStatus('error')
        onUnitsCountChangeRef.current?.(0)
        setLookupError(
          isTimeout
            ? tRef.current('catastro.lookupTimeout')
            : tRef.current('catastro.lookupError'),
        )
        // Clear the cached fetchKey so editing-then-coming-back to the same
        // address re-tries instead of being stuck in the error state.
        lastFetchedRef.current = null
      })

    return () => controller.abort()
    // Depending only on `mode` + `resolvedAddress` is intentional: the
    // callbacks and translator are mirrored into refs above so identity
    // churn there cannot abort an in-flight lookup. See the long-form
    // comment near the ref declarations for the failure mode this avoids.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, resolvedAddress])

  // Show the "Continuar sin Catastro" affordance after a few seconds of
  // sustained loading. Reset whenever lookupStatus changes so a fresh
  // address starts from a clean countdown.
  useEffect(() => {
    if (lookupStatus !== 'loading') {
      setShowSkipOption(false)
      return
    }
    const timer = setTimeout(() => setShowSkipOption(true), SKIP_OPTION_AFTER_MS)
    return () => clearTimeout(timer)
  }, [lookupStatus])

  const handleSkipCatastro = useCallback(() => {
    fetchControllerRef.current?.abort()
    fetchControllerRef.current = null
    setUnits([])
    setLookupStatus('error')
    setLookupError(t('catastro.lookupSkipped'))
    setShowSkipOption(false)
    onUnitsCountChange?.(0)
    // Pin the fetchKey so we don't immediately re-trigger the lookup the
    // next time this effect runs; the user explicitly opted out.
  }, [onUnitsCountChange, t])

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
          // Pass through directly. The previous wrapper here reset
          // `lastFetchedRef.current = null` and forced lookupStatus to
          // 'loading' on every onResolvedAddress call. AddressSearch
          // fires onSelect multiple times during a single user
          // interaction (suggestion click → handleSelect; portal commit
          // → commitPortal; same-frame input edit → handleInputChange),
          // and the wrapper turned each one into a fresh non-deduped
          // Catastro POST that aborted its predecessor — observed as 6+
          // overlapping POSTs and a permanently-stuck spinner when the
          // tail abort got there before the response was applied.
          // The Catastro-by-address useEffect below already handles
          // dedup + loading state when a real new address arrives.
          onResolvedAddress={onResolvedAddress}
          submitting={submitting}
        />
      ) : (
        <CadastralReferenceSearch
          onResolved={handleReferenceResolved}
          disabled={submitting}
        />
      )}

      {lookupStatus === 'loading' && (
        <div className="flex flex-col gap-xs">
          <div className="flex items-center gap-sm rounded-lg border border-line bg-surface-tint px-sm py-2 text-xs text-ink-secondary">
            <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
            {t('catastro.loading')}
          </div>
          {showSkipOption && (
            <button
              type="button"
              onClick={handleSkipCatastro}
              className="self-start text-xs font-medium text-primary underline-offset-2 hover:underline"
            >
              {t('catastro.skipWait')}
            </button>
          )}
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
