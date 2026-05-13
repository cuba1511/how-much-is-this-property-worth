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
    <div className="card-surface p-lg">
      {lead?.fullName && (
        <p className="mb-xs text-header-md font-semibold text-ink">
          {t('results.cta.greeting', { name: lead.fullName.split(' ')[0] })}
        </p>
      )}

      {totalTransactions != null && totalTransactions > 0 && (
        <p className="mb-md text-text-md text-ink-secondary">
          {t('results.cta.basedOn', { count: totalTransactions })}
        </p>
      )}

      <div className="alert-warning mb-md flex items-center gap-sm rounded-md border border-line-warning/40 p-md">
        <Clock className="h-5 w-5 shrink-0 text-warning-fg" />
        <p className="text-text-md">{t('results.cta.expiresIn')}</p>
      </div>

      <div className="flex flex-col gap-sm sm:flex-row">
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
