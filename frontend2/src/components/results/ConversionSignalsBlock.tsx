import { useTranslation } from 'react-i18next'
import { Clock, PhoneCall, FileText } from 'lucide-react'
import type { LeadInfo } from '@/lib/types'

interface ConversionSignalsBlockProps {
  lead?: LeadInfo
  totalTransactions?: number
}

export function ConversionSignalsBlock({ lead, totalTransactions }: ConversionSignalsBlockProps) {
  const { t } = useTranslation()

  return (
    <div className="rounded-2xl border border-line bg-surface p-lg shadow-card">
      {lead?.fullName && (
        <p className="text-lg font-semibold text-ink mb-xs">
          {t('results.cta.greeting', { name: lead.fullName.split(' ')[0] })}
        </p>
      )}

      {totalTransactions != null && totalTransactions > 0 && (
        <p className="text-sm text-ink-secondary mb-md">
          {t('results.cta.basedOn', { count: totalTransactions })}
        </p>
      )}

      <div className="flex items-center gap-sm rounded-xl bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 p-md mb-md">
        <Clock className="h-5 w-5 text-amber-600 shrink-0" />
        <p className="text-sm text-amber-800 dark:text-amber-300">{t('results.cta.expiresIn')}</p>
      </div>

      <div className="flex flex-col sm:flex-row gap-sm">
        <button type="button" className="btn-primary flex-1">
          <PhoneCall className="h-4 w-4" />
          {t('results.cta.talkToAdvisor')}
        </button>
        <button type="button" className="btn-secondary flex-1">
          <FileText className="h-4 w-4" />
          {t('results.cta.requestPdf')}
        </button>
      </div>
    </div>
  )
}
