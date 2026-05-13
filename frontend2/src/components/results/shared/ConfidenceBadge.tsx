import { useTranslation } from 'react-i18next'
import { ShieldCheck, ShieldAlert, ShieldQuestion } from 'lucide-react'
import type { ConfidenceLevel } from '@/lib/results'

const config: Record<ConfidenceLevel, { icon: typeof ShieldCheck; className: string }> = {
  high: { icon: ShieldCheck, className: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400' },
  medium: { icon: ShieldAlert, className: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400' },
  low: { icon: ShieldQuestion, className: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400' },
}

interface ConfidenceBadgeProps {
  level: ConfidenceLevel
}

export function ConfidenceBadge({ level }: ConfidenceBadgeProps) {
  const { t } = useTranslation()
  const { icon: Icon, className } = config[level]
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${className}`}>
      <Icon className="h-3.5 w-3.5" />
      {t(`results.confidence.${level}`)}
    </span>
  )
}
