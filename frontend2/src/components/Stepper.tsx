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

  const btn =
    'flex h-10 w-10 items-center justify-center rounded-full bg-secondary text-secondary-foreground ' +
    'transition-colors hover:bg-secondary-hover active:bg-primary/15 ' +
    'disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-ink-disabled'

  return (
    <div className="flex flex-col gap-xs">
      {label && (
        <label className="text-text-md font-medium text-ink">{label}</label>
      )}
      <div className="inline-flex items-center gap-md rounded-input bg-page px-md py-xs">
        <button
          type="button"
          onClick={decrement}
          disabled={disabled || value <= min}
          aria-label={label ? t('stepper.decrease', { label }) : t('stepper.decreaseDefault')}
          className={btn}
        >
          <Minus className="h-4 w-4" />
        </button>
        <span
          className="min-w-[2.5rem] select-none text-center text-header-md font-semibold tabular-nums text-ink"
          aria-live="polite"
        >
          {value}
        </span>
        <button
          type="button"
          onClick={increment}
          disabled={disabled || value >= max}
          aria-label={label ? t('stepper.increase', { label }) : t('stepper.increaseDefault')}
          className={btn}
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>
      {error && <p className="text-text-sm text-destructive">{error}</p>}
    </div>
  )
}
