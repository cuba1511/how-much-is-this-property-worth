import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Clock, MailCheck, PhoneCall, Download, Loader2 } from 'lucide-react'
import type { LeadInfo, ValuationRequest } from '@/lib/types'
import { downloadReportPdf } from '@/lib/api'

interface ConversionSignalsBlockProps {
  lead?: LeadInfo
  request?: ValuationRequest
  totalTransactions?: number
}

export function ConversionSignalsBlock({
  lead,
  request,
  totalTransactions,
}: ConversionSignalsBlockProps) {
  const { t } = useTranslation()
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState<string | null>(null)

  async function handleDownload() {
    if (!request) return
    setDownloading(true)
    setDownloadError(null)
    try {
      await downloadReportPdf(request)
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : t('results.cta.downloadError'))
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="rounded-2xl border border-line bg-surface p-lg shadow-card">
      {lead?.full_name && (
        <p className="text-lg font-semibold text-ink mb-xs">
          {t('results.cta.greeting', { name: lead.full_name.split(' ')[0] })}
        </p>
      )}

      {totalTransactions != null && totalTransactions > 0 && (
        <p className="text-sm text-ink-secondary mb-md">
          {t('results.cta.basedOn', { count: totalTransactions })}
        </p>
      )}

      {lead?.email && (
        <div className="flex items-center gap-sm rounded-xl bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 p-md mb-sm">
          <MailCheck className="h-5 w-5 text-emerald-600 shrink-0" />
          <p className="text-sm text-emerald-800 dark:text-emerald-300">
            {t('results.cta.emailSent', { email: lead.email })}
          </p>
        </div>
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
        <button
          type="button"
          className="btn-secondary flex-1"
          onClick={handleDownload}
          disabled={downloading || !request}
        >
          {downloading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Download className="h-4 w-4" />
          )}
          {downloading ? t('results.cta.downloadingPdf') : t('results.cta.downloadPdf')}
        </button>
      </div>

      {downloadError && (
        <p className="mt-sm text-sm text-destructive" role="alert">
          {downloadError}
        </p>
      )}
    </div>
  )
}
