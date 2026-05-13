import { useTranslation } from 'react-i18next'
import { ShieldCheck, ShieldAlert, ShieldQuestion } from 'lucide-react'
import type { ConfidenceLevel } from '@/lib/results'

/**
 * Confidence badge — semantic status tokens.
 *   high   → success
 *   medium → warning
 *   low    → error (destructive)
 */
const config: Record<ConfidenceLevel, { icon: typeof ShieldCheck; className: string }> = {
  high:   { icon: ShieldCheck,    className: 'alert-success' },
  medium: { icon: ShieldAlert,    className: 'alert-warning' },
  low:    { icon: ShieldQuestion, className: 'alert-error' },
}

interface ConfidenceBadgeProps {
  level: ConfidenceLevel
}

export function ConfidenceBadge({ level }: ConfidenceBadgeProps) {
  const { t } = useTranslation()
  const { icon: Icon, className } = config[level]
  return (
    <span className={`inline-flex items-center gap-xs rounded-pill px-3 py-0-5 text-text-sm font-medium ${className}`}>
      <Icon className="h-3.5 w-3.5" />
      {t(`results.confidence.${level}`)}
    </span>
  )
}
