import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Loader2,
  MapPin,
  Search,
  BarChart3,
  Building2,
  Calculator,
  FileText,
  type LucideIcon,
} from 'lucide-react'

type PhaseKey = 'geocoding' | 'searching' | 'processing' | 'pricing' | 'adjusting' | 'finalizing'

interface Phase {
  key: PhaseKey
  from: number
  icon: LucideIcon
}

const PHASES: Phase[] = [
  { key: 'geocoding', from: 0, icon: MapPin },
  { key: 'searching', from: 3, icon: Search },
  { key: 'processing', from: 10, icon: Building2 },
  { key: 'pricing', from: 22, icon: BarChart3 },
  { key: 'adjusting', from: 38, icon: Calculator },
  { key: 'finalizing', from: 55, icon: FileText },
]

// Asymptotic ease-out: caps at 92% so the bar never "lies" about being done.
// tau=22 → ~63% at 22s, ~82% at 38s, ~92% at 60s, plateaus afterwards.
const PROGRESS_CAP = 0.92
const TAU_SECONDS = 22

function computeProgress(elapsed: number, active: boolean): number {
  if (!active) return 1
  return Math.min(PROGRESS_CAP, 1 - Math.exp(-elapsed / TAU_SECONDS))
}

function pickPhase(elapsed: number): Phase {
  let current = PHASES[0]
  for (const phase of PHASES) {
    if (elapsed >= phase.from) current = phase
  }
  return current
}

interface LeadAnalyzingProgressProps {
  active: boolean
}

export function LeadAnalyzingProgress({ active }: LeadAnalyzingProgressProps) {
  const { t } = useTranslation()
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!active) return
    const start = performance.now()
    const id = window.setInterval(() => {
      setElapsed((performance.now() - start) / 1000)
    }, 200)
    return () => window.clearInterval(id)
  }, [active])

  const progress = computeProgress(elapsed, active)
  const phase = pickPhase(elapsed)
  const PhaseIcon = phase.icon

  return (
    <div
      className="flex flex-col gap-md py-sm"
      role="status"
      aria-live="polite"
      aria-busy={active}
    >
      <div className="flex flex-col items-center gap-sm text-center">
        <div className="relative">
          <div className="absolute inset-0 animate-ping rounded-full bg-primary/20" />
          <div className="relative flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
          </div>
        </div>
        <p
          key={phase.key}
          className="flex items-center gap-xs text-sm font-medium text-ink-secondary animate-chat-bubble-in"
        >
          <PhaseIcon className="h-4 w-4 text-primary" />
          {t(`lead.analyzing.phases.${phase.key}`)}
        </p>
      </div>

      <div
        className="relative h-2 w-full overflow-hidden rounded-pill bg-primary/10"
        role="progressbar"
        aria-valuenow={Math.round(progress * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className="absolute inset-y-0 left-0 rounded-pill bg-primary transition-[width] duration-500 ease-out"
          style={{ width: `${progress * 100}%` }}
        />
      </div>

      <div className="flex items-center justify-between text-xs text-ink-muted">
        <span>{t('lead.analyzing.elapsed', { seconds: Math.floor(elapsed) })}</span>
        <span>{Math.round(progress * 100)}%</span>
      </div>

      <p className="text-center text-xs text-ink-muted">
        {t('lead.analyzing.hint')}
      </p>
    </div>
  )
}
