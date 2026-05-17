import { useFormContext } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { IntentFieldSelect } from '@/components/IntentFieldSelect'
import type { ValuationRequestForm, ValuationIntent } from '@/lib/schemas'
import { rentTimelines, sellReasons, sellTimelines } from '@/lib/schemas'

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
  const rentTimeline = watch('rentTimeline')

  function selectIntent(value: ValuationIntent) {
    if (submitting) return
    setValue('valuationIntent', value, { shouldValidate: true })
    if (value !== 'sell') {
      setValue('sellReason', undefined)
      setValue('sellTimeline', undefined)
    }
    if (value !== 'rent_out') {
      setValue('rentTimeline', undefined)
    }
  }

  return (
    <div className="flex flex-col gap-md">
      <div>
        <h2 className="text-base font-semibold text-ink">{t('intent.title')}</h2>
        <p className="mt-0.5 text-sm text-ink-secondary">{t('intent.subtitle')}</p>
      </div>

      <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line">
        {INTENT_OPTIONS.map((value) => {
          const selected = intent === value
          return (
            <li key={value}>
              <button
                type="button"
                disabled={submitting}
                onClick={() => selectIntent(value)}
                className={`flex w-full items-center justify-between gap-md px-md py-3.5 text-left text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
                  selected ? 'bg-primary/5' : 'hover:bg-surface-tint'
                }`}
              >
                <span className={selected ? 'font-medium text-ink' : 'text-ink-secondary'}>
                  {t(`intent.options.${value}`)}
                </span>
                <span
                  className={`flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full border-2 transition-colors ${
                    selected ? 'border-primary bg-primary' : 'border-ink-muted/60'
                  }`}
                  aria-hidden
                >
                  {selected && <span className="h-1.5 w-1.5 rounded-full bg-white" />}
                </span>
              </button>

              {value === 'sell' && selected && (
                <div className="space-y-md border-t border-line bg-surface-tint/40 px-md py-md">
                  <IntentFieldSelect
                    id="sell-reason"
                    label={t('intent.sellReasonLabel')}
                    value={sellReason}
                    options={sellReasons}
                    optionLabel={(r) => t(`intent.sellReasons.${r}`)}
                    onChange={(r) =>
                      setValue('sellReason', r, { shouldValidate: true })
                    }
                    disabled={submitting}
                    error={errors.sellReason ? t('intent.sellReasonError') : undefined}
                  />
                  <IntentFieldSelect
                    id="sell-timeline"
                    label={t('intent.sellTimelineLabel')}
                    value={sellTimeline}
                    options={sellTimelines}
                    optionLabel={(tl) => t(`intent.sellTimelines.${tl}`)}
                    onChange={(tl) =>
                      setValue('sellTimeline', tl, { shouldValidate: true })
                    }
                    disabled={submitting}
                    error={errors.sellTimeline ? t('intent.sellTimelineError') : undefined}
                  />
                </div>
              )}

              {value === 'rent_out' && selected && (
                <div className="border-t border-line bg-surface-tint/40 px-md py-md">
                  <IntentFieldSelect
                    id="rent-timeline"
                    label={t('intent.rentTimelineLabel')}
                    value={rentTimeline}
                    options={rentTimelines}
                    optionLabel={(tl) => t(`intent.rentTimelines.${tl}`)}
                    onChange={(tl) =>
                      setValue('rentTimeline', tl, { shouldValidate: true })
                    }
                    disabled={submitting}
                    centeredLabel
                    error={errors.rentTimeline ? t('intent.rentTimelineError') : undefined}
                  />
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

