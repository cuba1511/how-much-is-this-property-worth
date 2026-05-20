import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FileSearch, Loader2, MapPin, Search } from 'lucide-react'
import { lookupByCadastralReference, ValuationError } from '@/lib/api'
import type {
  CadastralReferenceLookupResponse,
  CadastralUnit,
  ResolvedAddress,
} from '@/lib/types'

export interface CadastralReferenceSearchProps {
  onResolved: (args: {
    /** May be null when Catastro returned the property but geocoding failed.
     *  The parent decides whether to allow continuing without lat/lon. */
    resolvedAddress: ResolvedAddress | null
    units: CadastralUnit[]
    isParcel: boolean
    referenceLabel: string | null
  }) => void
  disabled?: boolean
}

/**
 * Alternative entry point to the valuation flow for users who already know
 * their Catastro RC. We accept both 14-char (parcela) and 20-char (inmueble)
 * references; the backend disambiguates and returns the matching unit(s).
 *
 * Submitting here calls `/api/catastro/by-reference` which geocodes the
 * Catastro address via Nominatim so the rest of the pipeline (Idealista
 * scrape, map, etc.) gets a normal `ResolvedAddress`.
 */
export function CadastralReferenceSearch({
  onResolved,
  disabled = false,
}: CadastralReferenceSearchProps) {
  const { t } = useTranslation()
  const [value, setValue] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmation, setConfirmation] = useState<string | null>(null)

  const trimmed = value.replace(/\s+/g, '').replace(/-/g, '')
  const lengthValid = trimmed.length === 14 || trimmed.length === 20
  const canSubmit = !submitting && !disabled && lengthValid

  async function handleSubmit(e?: React.FormEvent) {
    e?.preventDefault()
    if (!canSubmit) return
    setSubmitting(true)
    setError(null)
    setConfirmation(null)
    try {
      const response: CadastralReferenceLookupResponse = await lookupByCadastralReference(
        trimmed,
      )
      const label = response.resolved_address?.label ?? response.catastro_address_label ?? null
      if (label) {
        setConfirmation(
          response.is_parcel
            ? t('catastro.reference.parcelHint')
            : t('catastro.reference.addressResolved', { label }),
        )
      }
      onResolved({
        resolvedAddress: response.resolved_address,
        units: response.units,
        isParcel: response.is_parcel,
        referenceLabel: label,
      })
    } catch (err) {
      if (err instanceof ValuationError) {
        setError(err.detail ?? t('catastro.reference.lookupError'))
      } else {
        setError(t('catastro.reference.lookupError'))
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-sm">
      <label
        htmlFor="cadastral-reference-input"
        className="text-sm font-medium text-ink"
      >
        {t('catastro.reference.label')}
      </label>
      <p className="text-xs text-ink-muted">{t('catastro.reference.hint')}</p>

      <div className="flex flex-col gap-sm sm:flex-row">
        <div
          className={`flex flex-1 items-center gap-sm rounded-xl border bg-surface px-md py-sm transition-all ${
            disabled
              ? 'opacity-60 cursor-not-allowed border-line'
              : 'border-line focus-within:border-primary focus-within:ring-1 focus-within:ring-primary/20'
          }`}
        >
          <FileSearch className="h-4 w-4 shrink-0 text-ink-muted" />
          <input
            id="cadastral-reference-input"
            type="text"
            value={value}
            onChange={(e) => {
              setValue(e.target.value.toUpperCase())
              setConfirmation(null)
              setError(null)
            }}
            placeholder={t('catastro.reference.placeholder')}
            disabled={disabled || submitting}
            className="flex-1 bg-transparent text-sm text-ink placeholder:text-ink-muted outline-none disabled:cursor-not-allowed"
            spellCheck={false}
            autoComplete="off"
            maxLength={26}
          />
        </div>
        <button
          type="submit"
          disabled={!canSubmit}
          className="btn-primary flex items-center justify-center gap-2 whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              {t('catastro.reference.searching')}
            </>
          ) : (
            <>
              <Search className="h-4 w-4" />
              {t('catastro.reference.search')}
            </>
          )}
        </button>
      </div>

      {error && (
        <p className="text-xs text-destructive" role="alert">
          {error}
        </p>
      )}

      {confirmation && !error && (
        <div className="flex items-start gap-xs rounded-lg border border-primary/20 bg-primary/5 px-sm py-2">
          <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
          <p className="text-xs text-ink">{confirmation}</p>
        </div>
      )}
    </form>
  )
}
