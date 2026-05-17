import { useFormContext } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import type { ValuationRequestForm, ValuationIntent } from '@/lib/schemas'
import { sellReasons, sellTimelines } from '@/lib/schemas'

const INTENT_OPTIONS: ValuationIntent[] = [
  'sell',
  'buy',
  'rent_out',
  'rent',
  'info',
]

interface ValuationIntentStepProps {
  submitting?: boolean
}

export function ValuationIntentStep({ submitting = false }: ValuationIntentStepProps) {
  const { t } = useTranslation()
  const { watch, setValue, formState: { errors } } = useFormContext<ValuationRequestForm>()
  const intent = watch('valuationIntent')
  const sellReason = watch('sellReason')
  const sellTimeline = watch('sellTimeline')

  function selectIntent(value: ValuationIntent) {
    if (submitting) return
    setValue('valuationIntent', value, { shouldValidate: true })
    if (value !== 'sell') {
      setValue('sellReason', undefined)
      setValue('sellTimeline', undefined)
    }
  }

  return (
    <div className="flex flex-col gap-md">
      <div>
        <h2 className="text-base font-semibold text-ink">{t('intent.title')}</h2>
        <p className="mt-0.5 text-sm text-ink-secondary">{t('intent.subtitle')}</p>
      </div>

      <ul className="divide-y divide-line rounded-lg border border-line">
        {INTENT_OPTIONS.map((value) => {
          const selected = intent === value
          return (
            <li key={value}>
              <button
                type="button"
                disabled={submitting}
                onClick={() => selectIntent(value)}
                className={`flex w-full items-center justify-between gap-md px-md py-3 text-left text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
                  selected ? 'bg-primary/5' : 'hover:bg-surface-tint'
                }`}
              >
                <span className={selected ? 'font-medium text-ink' : 'text-ink-secondary'}>
                  {t(`intent.options.${value}`)}
                </span>
                <span
                  className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 ${
                    selected ? 'border-primary bg-primary' : 'border-ink-muted'
                  }`}
                  aria-hidden
                >
                  {selected && <span className="h-1.5 w-1.5 rounded-full bg-white" />}
                </span>
              </button>

              {value === 'sell' && selected && (
                <div className="space-y-sm border-t border-line bg-surface-tint/50 px-md py-md">
                  <div className="flex flex-col gap-xs">
                    <label htmlFor="sell-reason" className="text-xs font-medium text-ink">
                      {t('intent.sellReasonLabel')}
                    </label>
                    <select
                      id="sell-reason"
                      disabled={submitting}
                      value={sellReason ?? ''}
                      onChange={(e) =>
                        setValue('sellReason', e.target.value as ValuationRequestForm['sellReason'], {
                          shouldValidate: true,
                        })
                      }
                      className="rounded-lg border border-line bg-surface px-sm py-2 text-sm text-ink outline-none focus:border-primary focus:ring-1 focus:ring-primary/20"
                    >
                      <option value="">{t('intent.selectPlaceholder')}</option>
                      {sellReasons.map((r) => (
                        <option key={r} value={r}>
                          {t(`intent.sellReasons.${r}`)}
                        </option>
                      ))}
                    </select>
                    {errors.sellReason && (
                      <p className="text-xs text-destructive">{t('intent.sellReasonError')}</p>
                    )}
                  </div>

                  <div className="flex flex-col gap-xs">
                    <label htmlFor="sell-timeline" className="text-xs font-medium text-ink">
                      {t('intent.sellTimelineLabel')}
                    </label>
                    <select
                      id="sell-timeline"
                      disabled={submitting}
                      value={sellTimeline ?? ''}
                      onChange={(e) =>
                        setValue('sellTimeline', e.target.value as ValuationRequestForm['sellTimeline'], {
                          shouldValidate: true,
                        })
                      }
                      className="rounded-lg border border-line bg-surface px-sm py-2 text-sm text-ink outline-none focus:border-primary focus:ring-1 focus:ring-primary/20"
                    >
                      <option value="">{t('intent.selectPlaceholder')}</option>
                      {sellTimelines.map((tl) => (
                        <option key={tl} value={tl}>
                          {t(`intent.sellTimelines.${tl}`)}
                        </option>
                      ))}
                    </select>
                    {errors.sellTimeline && (
                      <p className="text-xs text-destructive">{t('intent.sellTimelineError')}</p>
                    )}
                  </div>
                </div>
              )}
            </li>
          )
        })}
      </ul>

      {errors.valuationIntent && (
        <p className="text-xs text-destructive">{t('intent.intentError')}</p>
      )}
    </div>
  )
}
