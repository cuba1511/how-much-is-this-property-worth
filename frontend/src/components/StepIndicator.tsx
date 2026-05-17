import { Check } from 'lucide-react'

interface Step {
  label: string
}

interface StepIndicatorProps {
  steps: Step[]
  /** Active step index (0-based). */
  current: number
  /** Highest step index the user has reached (for progressive reveal). */
  maxReached: number
  /** Total steps — used for screen readers only (future steps stay hidden). */
  totalSteps?: number
}

export function StepIndicator({ steps, current, maxReached, totalSteps }: StepIndicatorProps) {
  const total = totalSteps ?? steps.length
  const visibleSteps = steps.slice(0, maxReached + 1)

  return (
    <div className="flex flex-col gap-xs">
      <p className="sr-only" aria-live="polite">
        Paso {current + 1} de {total}: {steps[current]?.label}
      </p>

      <ol
        role="list"
        aria-label="Progreso"
        className="flex w-full items-center gap-sm"
      >
        {visibleSteps.map((step, i) => {
          const done = i < current
          const active = i === current
          const isLastVisible = i === visibleSteps.length - 1
          const connectorDone = i < current

          return (
            <li
              key={step.label}
              aria-current={active ? 'step' : undefined}
              className={`flex animate-in fade-in slide-in-from-left-2 items-center gap-sm duration-300 fill-mode-both ${
                isLastVisible ? 'flex-none' : 'min-w-0 flex-1'
              }`}
              style={{ animationDelay: i === maxReached && i > 0 ? '75ms' : '0ms' }}
            >
              <div className="flex shrink-0 items-center gap-xs">
                <div
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold transition-all ${
                    done || active
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-surface-muted text-ink-muted'
                  } ${active ? 'shadow-card' : ''}`}
                >
                  {done ? <Check className="h-4 w-4" /> : i + 1}
                </div>
                <span
                  className={`hidden text-sm font-medium whitespace-nowrap sm:inline ${
                    active ? 'text-ink' : done ? 'text-primary' : 'text-ink-muted'
                  }`}
                >
                  {step.label}
                </span>
              </div>
              {!isLastVisible && (
                <div
                  aria-hidden
                  className={`h-[2px] min-w-[12px] flex-1 rounded-full transition-colors ${
                    connectorDone ? 'bg-primary' : 'bg-surface-muted'
                  }`}
                />
              )}
            </li>
          )
        })}
      </ol>
    </div>
  )
}
