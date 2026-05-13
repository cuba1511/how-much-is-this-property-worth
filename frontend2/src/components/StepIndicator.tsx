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
    <ol
      role="list"
      aria-label="Progreso"
      className="flex w-full items-center gap-sm"
    >
      {steps.map((step, i) => {
        const done = i < current
        const active = i === current
        const isLast = i === steps.length - 1
        return (
          <li
            key={i}
            aria-current={active ? 'step' : undefined}
            className={`flex items-center gap-sm ${isLast ? 'flex-none' : 'flex-1'}`}
          >
            <div className="flex shrink-0 items-center gap-xs">
              <div
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold transition-all ${
                  done
                    ? 'bg-primary text-primary-foreground'
                    : active
                      ? 'bg-primary text-primary-foreground shadow-card'
                      : 'bg-surface-muted text-ink-muted'
                }`}
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
            {!isLast && (
              <div
                aria-hidden
                className={`h-[2px] min-w-[12px] flex-1 rounded-full transition-colors ${
                  done ? 'bg-primary' : 'bg-surface-muted'
                }`}
              />
            )}
          </li>
        )
      })}
    </ol>
  )
}
