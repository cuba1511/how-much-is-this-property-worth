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

// Rough timing model of the real backend pipeline. Stretched out so the
// progress bar tracks reality on slow scrapes (Idealista CAPTCHAs, Bright
// Data warm-up) instead of pegging to 92% in the first minute and looking
// frozen for the next 4+ minutes — which is what was happening in prod
// and made the user think the app died.
const PHASES: Phase[] = [
  { key: 'geocoding', from: 0, icon: MapPin },
  { key: 'searching', from: 10, icon: Search },
  { key: 'processing', from: 40, icon: Building2 },
  { key: 'pricing', from: 80, icon: BarChart3 },
  { key: 'adjusting', from: 130, icon: Calculator },
  { key: 'finalizing', from: 180, icon: FileText },
]

// Asymptotic ease-out: caps at 95% so the bar never "lies" about being done.
// tau=90 → ~63% at 90s, ~78% at 150s, ~90% at 230s, plateaus afterwards.
// Beyond the plateau we rotate the phase copy + show a "still working"
// hint so the user can tell progress is still happening on the backend.
const PROGRESS_CAP = 0.95
const TAU_SECONDS = 90

// Once this much time has passed without a result, surface an extra hint so
// the user understands the request is still alive (the backend just needs
// longer for some properties).
const LONG_RUNNING_HINT_AFTER_S = 180

function computeProgress(elapsed: number, active: boolean): number {
  if (!active) return 1
  return Math.min(PROGRESS_CAP, 1 - Math.exp(-elapsed / TAU_SECONDS))
}

function pickPhase(elapsed: number): Phase {
  // Past the last phase, rotate through the four user-visible phases on a
  // ~25s cycle so the copy keeps moving and the bar doesn't look frozen.
  const finalPhaseStart = PHASES[PHASES.length - 1].from
  if (elapsed >= finalPhaseStart + 25) {
    const rotation: PhaseKey[] = ['searching', 'processing', 'pricing', 'finalizing']
    const idx = Math.floor((elapsed - finalPhaseStart) / 25) % rotation.length
    const key = rotation[idx]
    return PHASES.find((p) => p.key === key) ?? PHASES[PHASES.length - 1]
  }
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

      {elapsed >= LONG_RUNNING_HINT_AFTER_S && (
        <p className="text-center text-xs text-ink-muted">
          {t('lead.analyzing.longRunningHint')}
        </p>
      )}
    </div>
  )
}
