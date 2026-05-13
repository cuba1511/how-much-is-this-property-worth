import { useTranslation } from 'react-i18next'
import { Minus, Plus } from 'lucide-react'

export interface StepperProps {
  value: number
  onChange: (value: number) => void
  min?: number
  max?: number
  label?: string
  error?: string
  disabled?: boolean
}

export function Stepper({
  value,
  onChange,
  min = 0,
  max = Infinity,
  label,
  error,
  disabled = false,
}: StepperProps) {
  const { t } = useTranslation()
  function decrement() {
    if (value > min) onChange(value - 1)
  }

  function increment() {
    if (value < max) onChange(value + 1)
  }

  return (
    <div className="flex flex-col gap-xs">
      {label && (
        <label className="text-sm font-medium text-ink">{label}</label>
      )}
      <div className="inline-flex items-center gap-sm">
        <button
          type="button"
          onClick={decrement}
          disabled={disabled || value <= min}
          aria-label={label ? t('stepper.decrease', { label }) : t('stepper.decreaseDefault')}
          className="flex h-9 w-9 items-center justify-center rounded-full text-primary transition-colors disabled:cursor-not-allowed disabled:opacity-30"
          style={{ backgroundColor: 'rgba(32, 80, 246, 0.1)' }}
        >
          <Minus className="h-4 w-4" />
        </button>
        <span
          className="min-w-[2rem] select-none text-center text-base font-semibold text-ink tabular-nums"
          aria-live="polite"
        >
          {value}
        </span>
        <button
          type="button"
          onClick={increment}
          disabled={disabled || value >= max}
          aria-label={label ? t('stepper.increase', { label }) : t('stepper.increaseDefault')}
          className="flex h-9 w-9 items-center justify-center rounded-full text-primary transition-colors disabled:cursor-not-allowed disabled:opacity-30"
          style={{ backgroundColor: 'rgba(32, 80, 246, 0.1)' }}
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}
