import { useState, useEffect, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { MapPin, Check, Search, X } from 'lucide-react'
import { autocompleteAddresses } from '@/lib/api'
import type { ResolvedAddress } from '@/lib/types'

export interface AddressSearchProps {
  onSelect: (address: ResolvedAddress | null) => void
  placeholder?: string
  disabled?: boolean
  /** Pre-fill when continuing from the hero or restoring state. */
  defaultAddress?: ResolvedAddress | null
}

export function AddressSearch({
  onSelect,
  placeholder,
  disabled = false,
  defaultAddress = null,
}: AddressSearchProps) {
  const { t } = useTranslation()
  const resolvedPlaceholder = placeholder ?? t('address.placeholder')
  const [query, setQuery] = useState(defaultAddress?.label ?? '')
  const [suggestions, setSuggestions] = useState<ResolvedAddress[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<ResolvedAddress | null>(defaultAddress)
  const [open, setOpen] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const search = useCallback(async (q: string) => {
    if (q.length < 3) {
      setSuggestions([])
      setOpen(false)
      return
    }
    // Cancel any in-flight request to avoid out-of-order results overwriting newer ones.
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setLoading(true)
    try {
      const data = await autocompleteAddresses(q, { limit: 5, signal: controller.signal })
      setSuggestions(data)
      setOpen(data.length > 0)
    } catch (err) {
      if ((err as { name?: string })?.name === 'AbortError') return
      setSuggestions([])
      setOpen(false)
    } finally {
      if (abortRef.current === controller) setLoading(false)
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

  function handleSelect(result: ResolvedAddress) {
    setSelected(result)
    setQuery(result.label)
    setSuggestions([])
    setOpen(false)
    onSelect(result)
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
        className={`flex items-center gap-sm border rounded-xl bg-surface px-md py-sm transition-all ${
          disabled
            ? 'opacity-60 cursor-not-allowed border-line'
            : selected
              ? 'border-primary ring-1 ring-primary/20'
              : 'border-line focus-within:border-primary focus-within:ring-1 focus-within:ring-primary/20'
        }`}
      >
        {selected ? (
          <Check className="w-4 h-4 text-primary shrink-0" />
        ) : loading ? (
          <svg
            className="w-4 h-4 shrink-0 text-primary animate-spin"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        ) : (
          <Search className="w-4 h-4 shrink-0 text-ink-muted" />
        )}
        <input
          type="text"
          value={query}
          onChange={handleInputChange}
          placeholder={resolvedPlaceholder}
          disabled={disabled}
          className="flex-1 bg-transparent outline-none text-ink placeholder:text-ink-muted text-sm disabled:cursor-not-allowed"
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
            className="text-ink-muted hover:text-ink transition-colors"
            aria-label={t('address.clearSearch')}
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {selected && (
        <div className="flex items-center gap-xs mt-xs px-sm">
          <MapPin className="w-3 h-3 text-primary" />
          <span className="text-xs text-primary font-medium">{t('address.confirmed')}</span>
        </div>
      )}

      {open && suggestions.length > 0 && (
        <ul
          role="listbox"
          aria-label={t('address.suggestions')}
          className="absolute z-[1001] mt-1 w-full bg-surface border border-line rounded-xl shadow-lift overflow-hidden"
        >
          {suggestions.map((s, idx) => (
            <li key={`${s.provider_id ?? idx}-${s.label}`} role="option" aria-selected={false}>
              <button
                type="button"
                className="w-full text-left px-md py-sm text-sm text-ink hover:bg-surface-tint transition-colors flex items-start gap-sm"
                onClick={() => handleSelect(s)}
              >
                <MapPin className="w-3.5 h-3.5 text-ink-muted shrink-0 mt-0.5" />
                <span className="line-clamp-2">{s.label}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
