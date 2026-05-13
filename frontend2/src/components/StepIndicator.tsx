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
    <div className="flex items-center gap-sm w-full">
      {steps.map((step, i) => {
        const done = i < current
        const active = i === current
        return (
          <div key={i} className="flex items-center gap-sm flex-1 last:flex-none">
            <div className="flex items-center gap-xs">
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
                className={`text-sm font-medium whitespace-nowrap hidden sm:inline ${
                  active ? 'text-ink' : done ? 'text-primary' : 'text-ink-muted'
                }`}
              >
                {step.label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div
                className={`h-[2px] flex-1 rounded-full transition-colors ${
                  done ? 'bg-primary' : 'bg-surface-muted'
                }`}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
