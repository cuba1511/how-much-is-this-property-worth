import { useState, useEffect, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { MapPin, Check, Search, X } from 'lucide-react'
import type { ResolvedAddress } from '@/lib/types'

interface NominatimResult {
  place_id: number
  display_name: string
  lat: string
  lon: string
  address: {
    road?: string
    house_number?: string
    postcode?: string
    city?: string
    town?: string
    village?: string
    municipality?: string
    county?: string
    state?: string
    country?: string
    neighbourhood?: string
    quarter?: string
    city_district?: string
  }
}

function toResolvedAddress(result: NominatimResult): ResolvedAddress {
  const addr = result.address
  const municipality =
    addr.municipality ?? addr.city ?? addr.town ?? addr.village ?? addr.county ?? ''
  return {
    label: result.display_name,
    lat: parseFloat(result.lat),
    lon: parseFloat(result.lon),
    municipality,
    province: addr.state ?? null,
    road: addr.road ?? null,
    house_number: addr.house_number ?? null,
    postcode: addr.postcode ?? null,
    neighbourhood: addr.neighbourhood ?? null,
    quarter: addr.quarter ?? null,
    city_district: addr.city_district ?? null,
    country: addr.country ?? null,
    provider: 'nominatim',
    provider_id: String(result.place_id),
  }
}

export interface AddressSearchProps {
  onSelect: (address: ResolvedAddress | null) => void
  placeholder?: string
  disabled?: boolean
}

export function AddressSearch({
  onSelect,
  placeholder,
  disabled = false,
}: AddressSearchProps) {
  const { t } = useTranslation()
  const resolvedPlaceholder = placeholder ?? t('address.placeholder')
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState<NominatimResult[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<ResolvedAddress | null>(null)
  const [open, setOpen] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const search = useCallback(async (q: string) => {
    if (q.length < 3) {
      setSuggestions([])
      setOpen(false)
      return
    }
    setLoading(true)
    try {
      const params = new URLSearchParams({
        q,
        format: 'json',
        limit: '5',
        addressdetails: '1',
        countrycodes: 'es',
      })
      const res = await fetch(`https://nominatim.openstreetmap.org/search?${params}`, {
        headers: { 'Accept-Language': 'es' },
      })
      const data: NominatimResult[] = await res.json()
      setSuggestions(data)
      setOpen(data.length > 0)
    } catch {
      setSuggestions([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (selected) return
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => void search(query), 350)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [query, search, selected])

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  function handleSelect(result: NominatimResult) {
    const resolved = toResolvedAddress(result)
    setSelected(resolved)
    setQuery(result.display_name)
    setSuggestions([])
    setOpen(false)
    onSelect(resolved)
  }

  function handleClear() {
    setSelected(null)
    setQuery('')
    setSuggestions([])
    setOpen(false)
    onSelect(null)
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (selected) {
      setSelected(null)
      onSelect(null)
    }
    setQuery(e.target.value)
  }

  return (
    <div ref={containerRef} className="relative w-full">
      <div
        className={[
          'flex items-center gap-sm rounded-input border bg-page px-md py-sm transition-all duration-fast',
          disabled
            ? 'cursor-not-allowed border-line opacity-60'
            : selected
              ? 'border-line-brand ring-2 ring-primary/20'
              : 'border-line focus-within:border-line-brand focus-within:ring-2 focus-within:ring-primary/20',
        ].join(' ')}
      >
        {selected ? (
          <Check className="h-4 w-4 shrink-0 text-brand" />
        ) : loading ? (
          <svg
            className="h-4 w-4 shrink-0 animate-spin text-brand"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        ) : (
          <Search className="h-4 w-4 shrink-0 text-ink-muted" />
        )}
        <input
          type="text"
          value={query}
          onChange={handleInputChange}
          placeholder={resolvedPlaceholder}
          disabled={disabled}
          className="flex-1 bg-transparent text-text-md text-ink outline-none placeholder:text-ink-muted disabled:cursor-not-allowed"
          autoComplete="off"
          aria-label={t('address.searchLabel')}
          aria-expanded={open}
          aria-haspopup="listbox"
          role="combobox"
        />
        {query && !disabled && (
          <button
            type="button"
            onClick={handleClear}
            className="text-ink-muted transition-colors hover:text-ink"
            aria-label={t('address.clearSearch')}
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {selected && (
        <div className="mt-xs flex items-center gap-xs px-sm">
          <MapPin className="h-3 w-3 text-brand" />
          <span className="text-text-sm font-medium text-brand">{t('address.confirmed')}</span>
        </div>
      )}

      {open && suggestions.length > 0 && (
        <ul
          role="listbox"
          aria-label={t('address.suggestions')}
          className="absolute z-[1001] mt-xs w-full overflow-hidden rounded-lg border border-line-subtle bg-card shadow-level-3"
        >
          {suggestions.map((s) => (
            <li key={s.place_id} role="option" aria-selected={false}>
              <button
                type="button"
                className="flex w-full items-start gap-sm px-md py-sm text-left text-text-md text-ink transition-colors hover:bg-surface-tint"
                onClick={() => handleSelect(s)}
              >
                <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-muted" />
                <span className="line-clamp-2">{s.display_name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
