import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ArrowRight,
  BarChart3,
  Clock,
  FileSearch,
  MapPin,
} from 'lucide-react'
import { AddressSearch } from '@/components/AddressSearch'
import { CadastralReferenceSearch } from '@/components/CadastralReferenceSearch'
import type {
  CadastralUnit,
  IdentificationMode,
  IdentificationStartPayload,
  ResolvedAddress,
} from '@/lib/types'

interface HeroSectionProps {
  onStart: (payload: IdentificationStartPayload) => void
}

const MODE_STORAGE_KEY = 'hv:hero:identification-mode'

function readPersistedMode(): IdentificationMode {
  if (typeof window === 'undefined') return 'address'
  try {
    const raw = window.localStorage.getItem(MODE_STORAGE_KEY)
    return raw === 'reference' ? 'reference' : 'address'
  } catch {
    return 'address'
  }
}

interface ReferenceResolution {
  resolvedAddress: ResolvedAddress | null
  units: CadastralUnit[]
  isParcel: boolean
  referenceLabel: string | null
}

export function HeroSection({ onStart }: HeroSectionProps) {
  const { t } = useTranslation()
  const [mode, setMode] = useState<IdentificationMode>(readPersistedMode)
  const [address, setAddress] = useState<ResolvedAddress | null>(null)
  const [reference, setReference] = useState<ReferenceResolution | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Persist mode so reload + "Hacer otra valoración" come back to the
  // search shape the user picked last time — sticky behavior across sessions.
  useEffect(() => {
    try {
      window.localStorage.setItem(MODE_STORAGE_KEY, mode)
    } catch {
      /* localStorage disabled (private mode, quota, etc.) — silently no-op. */
    }
  }, [mode])

  const canContinue =
    mode === 'address'
      ? Boolean(address?.house_number)
      : Boolean(reference && reference.units.length > 0)

  function handleModeChange(next: IdentificationMode) {
    if (next === mode) return
    setMode(next)
    setError(null)
    // Don't blow away the other mode's draft — when the user toggles back we
    // want their previous input to still be there. We only clear the error.
  }

  function handleContinue() {
    if (mode === 'address') {
      if (!address?.house_number) {
        setError(t('catastro.needStreetNumber'))
        return
      }
      setError(null)
      onStart({ mode: 'address', address })
      return
    }
    if (!reference || reference.units.length === 0) {
      setError(t('catastro.reference.lookupError'))
      return
    }
    if (!reference.resolvedAddress) {
      // Reference matched but Nominatim couldn't ubicate it — the rest of the
      // pipeline needs lat/lon, so we surface a warning and stop. User can
      // either re-search a more precise reference or fall back to the address
      // tab.
      setError(t('catastro.reference.geocodeWarning'))
      return
    }
    setError(null)
    onStart({
      mode: 'reference',
      address: reference.resolvedAddress,
      units: reference.units,
      // Auto-select when there's exactly one unit AND it's not a parcel
      // lookup (parcel = 14-char = multiple units possible inside).
      selectedUnit:
        reference.units.length === 1 && !reference.isParcel
          ? reference.units[0]
          : null,
      isParcel: reference.isParcel,
      referenceLabel: reference.referenceLabel,
    })
  }

  return (
    <section className="w-full bg-surface">
      <div className="grid min-h-[calc(100svh-4rem)] grid-cols-1 md:grid-cols-2">
        <div className="flex items-center justify-center px-md py-xl md:px-2xl">
          <div className="flex w-full max-w-[520px] flex-col items-start gap-md">
            <span className="inline-flex items-center gap-2 rounded-pill border border-line bg-surface-tint px-3 py-1 text-xs font-medium text-ink-secondary">
              <img
                src="/vistral-logo.svg"
                alt=""
                aria-hidden="true"
                width={14}
                height={14}
                className="h-3.5 w-3.5"
              />
              <span className="font-semibold text-ink">Vistral</span>
              <span className="text-ink-muted">·</span>
              <span>{t('hero.badge')}</span>
            </span>

            <h1 className="!my-0 text-balance text-[2rem] md:text-[2.5rem] font-semibold leading-[1.1] tracking-tight">
              {t('hero.title')}
              <span className="text-primary whitespace-nowrap">{t('hero.titleHighlight')}</span>
              {t('hero.titleEnd')}
            </h1>

            <p className="text-base leading-relaxed text-ink-secondary text-balance max-w-[460px]">
              {t('hero.subtitle')}
            </p>

            <div className="mt-xs flex w-full flex-col gap-sm">
              <div
                role="tablist"
                aria-label={t('catastro.tabs.address')}
                className="grid grid-cols-2 gap-2 rounded-2xl border border-line bg-surface-tint p-1"
              >
                <HeroModeTab
                  active={mode === 'address'}
                  onClick={() => handleModeChange('address')}
                  icon={<MapPin className="h-4 w-4" />}
                  label={t('catastro.tabs.address')}
                />
                <HeroModeTab
                  active={mode === 'reference'}
                  onClick={() => handleModeChange('reference')}
                  icon={<FileSearch className="h-4 w-4" />}
                  label={t('catastro.tabs.reference')}
                />
              </div>

              {mode === 'address' ? (
                <div className="flex w-full flex-col gap-sm sm:flex-row sm:items-start">
                  <div className="min-w-0 flex-1">
                    <AddressSearch
                      onSelect={(addr) => {
                        setAddress(addr)
                        if (addr?.house_number) setError(null)
                      }}
                      placeholder={t('hero.addressPlaceholder')}
                    />
                  </div>
                  <button
                    type="button"
                    onClick={handleContinue}
                    disabled={!canContinue}
                    className="btn-primary flex shrink-0 items-center justify-center gap-2 whitespace-nowrap px-6 py-3 text-sm disabled:cursor-not-allowed disabled:opacity-50 sm:self-stretch"
                  >
                    {t('hero.continue')}
                    <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
              ) : (
                <div className="flex w-full flex-col gap-sm">
                  <CadastralReferenceSearch
                    onResolved={(args) => {
                      setReference(args)
                      setError(null)
                    }}
                  />
                  <button
                    type="button"
                    onClick={handleContinue}
                    disabled={!canContinue}
                    className="btn-primary flex w-full shrink-0 items-center justify-center gap-2 whitespace-nowrap px-6 py-3 text-sm disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto sm:self-start"
                  >
                    {t('hero.continue')}
                    <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
              )}

              {error && (
                <p className="text-xs text-destructive" role="alert">
                  {error}
                </p>
              )}
              <span className="text-xs text-ink-muted">{t('hero.ctaCaption')}</span>
            </div>

            <ul className="mt-sm flex flex-col gap-xs">
              {[
                { icon: Clock, key: 'impacts.resultTime' },
                { icon: MapPin, key: 'impacts.realTimePrices' },
                { icon: BarChart3, key: 'impacts.propertiesSold' },
              ].map(({ icon: Icon, key }) => (
                <li
                  key={key}
                  className="inline-flex w-fit items-center gap-2 rounded-pill border border-line bg-surface px-3 py-1 text-xs text-ink-secondary"
                >
                  <Icon className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden="true" />
                  <span>{t(key)}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="relative min-h-[320px] overflow-hidden bg-surface-muted md:min-h-full">
          <img
            src="/piso.png"
            alt={t('hero.imageAlt')}
            className="absolute inset-0 h-full w-full object-cover [object-position:center_35%]"
            loading="eager"
            decoding="async"
          />
        </div>
      </div>
    </section>
  )
}

interface HeroModeTabProps {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  label: string
}

function HeroModeTab({ active, onClick, icon, label }: HeroModeTabProps) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`flex items-center justify-center gap-2 rounded-xl px-sm py-2 text-sm font-medium transition-all ${
        active
          ? 'bg-surface text-ink shadow-card border border-line'
          : 'text-ink-secondary hover:text-ink'
      }`}
    >
      {icon}
      {label}
    </button>
  )
}
