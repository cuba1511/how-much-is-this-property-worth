import { Check } from 'lucide-react'

interface Step {
  label: string
}

interface StepIndicatorProps {
  steps: Step[]
  current: number
}

export function StepIndicator({ steps, current }: StepIndicatorProps) {
  return (
    <ol className="flex w-full items-center gap-sm" aria-label="progress">
      {steps.map((step, i) => {
        const done = i < current
        const active = i === current
        return (
          <li
            key={i}
            className="flex flex-1 items-center gap-sm last:flex-none"
            aria-current={active ? 'step' : undefined}
          >
            <div className="flex items-center gap-xs">
              <span
                className={[
                  'flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-text-sm font-semibold transition-all duration-fast',
                  done
                    ? 'bg-primary text-primary-foreground'
                    : active
                      ? 'bg-primary text-primary-foreground shadow-card ring-4 ring-primary/15'
                      : 'bg-surface-muted text-ink-muted',
                ].join(' ')}
              >
                {done ? <Check className="h-4 w-4" /> : i + 1}
              </span>
              <span
                className={[
                  'hidden whitespace-nowrap text-text-md font-medium sm:inline',
                  active ? 'text-ink' : done ? 'text-brand' : 'text-ink-muted',
                ].join(' ')}
              >
                {step.label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <span
                aria-hidden
                className={[
                  'h-[2px] flex-1 rounded-full transition-colors duration-fast',
                  done ? 'bg-primary' : 'bg-surface-muted',
                ].join(' ')}
              />
            )}
          </li>
        )
      })}
    </ol>
  )
}
