import { Check } from 'lucide-react'

interface Step {
  label: string
}

interface StepIndicatorProps {
  steps: Step[]
  /** Active step index (0-based). */
  current: number
}

export function StepIndicator({ steps, current }: StepIndicatorProps) {
  const lastIndex = steps.length - 1

  return (
    <div className="flex flex-col gap-xs">
      <p className="sr-only" aria-live="polite">
        Paso {current + 1} de {steps.length}: {steps[current]?.label}
      </p>

      <ol role="list" aria-label="Progreso" className="flex w-full items-center">
        {steps.map((step, i) => {
          const done = i < current
          const active = i === current
          const upcoming = i > current
          const isLast = i === lastIndex

          return (
            <li
              key={step.label}
              aria-current={active ? 'step' : undefined}
              className={`flex items-center ${isLast ? 'shrink-0' : 'min-w-0 flex-1'}`}
            >
              <div
                className={`flex shrink-0 items-center gap-xs transition-opacity ${
                  upcoming ? 'opacity-40' : ''
                }`}
              >
                <div
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                    done || active
                      ? 'bg-primary text-primary-foreground'
                      : 'border border-line bg-surface text-ink-muted'
                  } ${active ? 'shadow-card' : ''}`}
                >
                  {done ? <Check className="h-4 w-4" /> : i + 1}
                </div>
                <span
                  className={`hidden max-w-[5.5rem] truncate text-sm font-medium sm:inline ${
                    active ? 'text-ink' : done ? 'text-primary' : 'text-ink-muted'
                  }`}
                >
                  {step.label}
                </span>
              </div>
              {!isLast && (
                <div
                  aria-hidden
                  className={`mx-2 h-[2px] min-w-[12px] flex-1 rounded-full ${
                    i < current ? 'bg-primary' : 'bg-surface-muted'
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
