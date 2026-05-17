import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

interface IntentFieldSelectProps<T extends string> {
  id: string
  label: string
  value: T | undefined
  options: readonly T[]
  optionLabel: (value: T) => string
  onChange: (value: T) => void
  disabled?: boolean
  error?: string
  /** Center question above control (Fotocasa-style for rent timeline). */
  centeredLabel?: boolean
}

export function IntentFieldSelect<T extends string>({
  id,
  label,
  value,
  options,
  optionLabel,
  onChange,
  disabled = false,
  error,
  centeredLabel = false,
}: IntentFieldSelectProps<T>) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const selectedLabel = value ? optionLabel(value) : null

  return (
    <div ref={containerRef} className="flex flex-col gap-xs">
      <label
        htmlFor={id}
        className={cn(
          'text-sm font-medium text-ink',
          centeredLabel && 'text-center text-ink-secondary font-normal',
        )}
      >
        {label}
      </label>

      <div className="relative">
        <button
          id={id}
          type="button"
          disabled={disabled}
          aria-haspopup="listbox"
          aria-expanded={open}
          onClick={() => !disabled && setOpen((o) => !o)}
          className={cn(
            'flex w-full items-center justify-between gap-sm rounded-xl border bg-surface px-md py-3 text-left text-sm transition-all',
            disabled && 'cursor-not-allowed opacity-60',
            error
              ? 'border-destructive ring-1 ring-destructive/20'
              : open
                ? 'border-primary ring-1 ring-primary/20'
                : value
                  ? 'border-primary/40'
                  : 'border-line hover:border-primary/30',
          )}
        >
          <span className={selectedLabel ? 'text-ink' : 'text-ink-muted'}>
            {selectedLabel ?? t('intent.selectPlaceholder')}
          </span>
          <ChevronDown
            className={cn(
              'h-4 w-4 shrink-0 text-ink-muted transition-transform',
              open && 'rotate-180 text-primary',
            )}
            aria-hidden
          />
        </button>

        {open && !disabled && (
          <ul
            role="listbox"
            aria-labelledby={id}
            className="absolute z-[1001] mt-1 max-h-56 w-full overflow-auto rounded-xl border border-line bg-surface py-1 shadow-lift"
          >
            {options.map((opt) => {
              const isSelected = value === opt
              return (
                <li key={opt} role="option" aria-selected={isSelected}>
                  <button
                    type="button"
                    className={cn(
                      'flex w-full items-center justify-between gap-sm px-md py-2.5 text-left text-sm transition-colors',
                      isSelected
                        ? 'bg-primary/5 text-ink font-medium'
                        : 'text-ink-secondary hover:bg-surface-tint hover:text-ink',
                    )}
                    onClick={() => {
                      onChange(opt)
                      setOpen(false)
                    }}
                  >
                    <span>{optionLabel(opt)}</span>
                    {isSelected && <Check className="h-4 w-4 shrink-0 text-primary" aria-hidden />}
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      {error && (
        <p className="text-xs text-destructive" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}
