import { Check } from 'lucide-react'

interface Step {
  label: string
}

interface StepIndicatorProps {
  steps: Step[]
  current: number
  maxRevealed: number
}

export function StepIndicator({ steps, current, maxRevealed }: StepIndicatorProps) {
  const visibleSteps = steps.slice(0, maxRevealed + 1)
  const total = steps.length

  return (
    <div className="min-h-10 w-full border-b border-line/60 pb-md">
      <p className="sr-only" aria-live="polite">
        Paso {current + 1} de {visibleSteps.length}: {steps[current]?.label}
      </p>

      <div className="flex items-center justify-between gap-md">
        <ol role="list" aria-label="Progreso" className="flex min-w-0 flex-1 items-center">
          {visibleSteps.map((step, i) => {
            const done = i < current
            const active = i === current
            const isLastVisible = i === visibleSteps.length - 1

            return (
              <li
                key={step.label}
                aria-current={active ? 'step' : undefined}
                className="flex shrink-0 items-center"
              >
                <div className="flex items-center gap-2">
                  <div
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                      done || active
                        ? 'bg-primary text-primary-foreground'
                        : 'border border-line bg-surface text-ink-muted'
                    } ${active ? 'shadow-card' : ''}`}
                  >
                    {done ? <Check className="h-4 w-4" strokeWidth={2.5} /> : i + 1}
                  </div>
                  <span
                    className={`hidden whitespace-nowrap text-sm font-medium sm:inline ${
                      active ? 'text-ink' : done ? 'text-primary' : 'text-ink-muted'
                    }`}
                  >
                    {step.label}
                  </span>
                </div>
                {!isLastVisible && (
                  <div
                    aria-hidden
                    className={`mx-3 h-0.5 w-10 shrink-0 rounded-full sm:mx-4 sm:w-14 ${
                      i < current ? 'bg-primary' : 'bg-surface-muted'
                    }`}
                  />
                )}
              </li>
            )
          })}
        </ol>

        <span
          className="shrink-0 text-xs font-medium tabular-nums text-ink-muted"
          aria-hidden
        >
          {current + 1}/{total}
        </span>
      </div>

      <p className="mt-2 truncate text-sm font-medium text-ink sm:hidden">
        {steps[current]?.label}
      </p>
    </div>
  )
}
