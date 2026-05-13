import { Controller, useFormContext } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Loader2, Sparkles, Home, Wrench, Ruler, type LucideIcon } from 'lucide-react'
import { Stepper } from '@/components/Stepper'
import type { ValuationRequestForm, PropertyCondition } from '@/lib/schemas'

const CONDITIONS: { value: PropertyCondition; labelKey: string; icon: LucideIcon }[] = [
  { value: 'obra_nueva', labelKey: 'condition.newBuild', icon: Sparkles },
  { value: 'buen_estado', labelKey: 'condition.good', icon: Home },
  { value: 'a_reformar', labelKey: 'condition.toRenovate', icon: Wrench },
]

interface PropertyDetailsStepProps {
  submitting: boolean
}

export function PropertyDetailsStep({ submitting }: PropertyDetailsStepProps) {
  const { t } = useTranslation()
  const { control, watch, setValue, formState: { errors } } = useFormContext<ValuationRequestForm>()
  const selectedCondition = watch('propertyCondition')

  return (
    <div className="flex flex-col gap-lg">
      {/* Property condition */}
      <fieldset className="flex flex-col gap-sm">
        <legend className="text-text-md font-medium text-ink">{t('condition.label')}</legend>
        <div className="grid grid-cols-3 gap-sm">
          {CONDITIONS.map(({ value, labelKey, icon: Icon }) => {
            const active = selectedCondition === value
            return (
              <button
                key={value}
                type="button"
                disabled={submitting}
                onClick={() => setValue('propertyCondition', value, { shouldValidate: true })}
                aria-pressed={active}
                className={[
                  'group flex flex-col items-center gap-xs rounded-lg border-2 px-sm py-md transition-all',
                  'disabled:cursor-not-allowed disabled:opacity-60',
                  active
                    ? 'border-line-brand bg-primary/5 shadow-card'
                    : 'border-line bg-card hover:border-line-brand/40 hover:bg-surface-tint',
                ].join(' ')}
              >
                <Icon
                  aria-hidden
                  strokeWidth={1.5}
                  className={[
                    'h-7 w-7 transition-all group-hover:scale-110',
                    active ? 'text-brand' : 'text-ink-secondary',
                  ].join(' ')}
                />
                <span
                  className={[
                    'text-center text-text-sm font-semibold',
                    active ? 'text-brand' : 'text-ink-secondary',
                  ].join(' ')}
                >
                  {t(labelKey)}
                </span>
              </button>
            )
          })}
        </div>
        {errors.propertyCondition && (
          <p className="text-text-sm text-destructive">{t('condition.error')}</p>
        )}
      </fieldset>

      {/* m² */}
      <div className="flex flex-col gap-xs">
        <label htmlFor="m2" className="text-text-md font-medium text-ink">
          {t('details.area')}
        </label>
        <Controller
          name="m2"
          control={control}
          render={({ field }) => (
            <div
              className={[
                'flex items-center gap-sm rounded-input border bg-page px-md py-sm transition-all',
                errors.m2
                  ? 'border-line-error ring-2 ring-destructive/15'
                  : 'border-line focus-within:border-line-brand focus-within:ring-2 focus-within:ring-primary/20',
              ].join(' ')}
            >
              <Ruler aria-hidden strokeWidth={1.5} className="h-[18px] w-[18px] shrink-0 text-ink-muted" />
              <input
                {...field}
                id="m2"
                type="number"
                inputMode="numeric"
                min={20}
                max={500}
                placeholder={t('details.areaPlaceholder')}
                disabled={submitting}
                onChange={(e) =>
                  field.onChange(e.target.value === '' ? undefined : Number(e.target.value))
                }
                value={field.value ?? ''}
                className="w-full bg-transparent text-text-md text-ink outline-none placeholder:text-ink-muted disabled:cursor-not-allowed"
                aria-describedby={errors.m2 ? 'm2-error' : undefined}
                aria-invalid={!!errors.m2}
              />
            </div>
          )}
        />
        {errors.m2 && (
          <p id="m2-error" className="text-text-sm text-destructive">
            {errors.m2.message?.includes('20')
              ? t('details.areaMin')
              : errors.m2.message?.includes('500')
                ? t('details.areaMax')
                : t('details.areaRequired')}
          </p>
        )}
      </div>

      {/* Bedrooms & Bathrooms */}
      <div className="grid grid-cols-2 gap-md">
        <Controller
          name="bedrooms"
          control={control}
          render={({ field }) => (
            <Stepper
              value={field.value}
              onChange={field.onChange}
              min={0}
              max={10}
              label={t('details.bedrooms')}
              error={errors.bedrooms?.message}
              disabled={submitting}
            />
          )}
        />
        <Controller
          name="bathrooms"
          control={control}
          render={({ field }) => (
            <Stepper
              value={field.value}
              onChange={field.onChange}
              min={1}
              max={5}
              label={t('details.bathrooms')}
              error={errors.bathrooms?.message}
              disabled={submitting}
            />
          )}
        />
      </div>

      {/* Submit */}
      <button
        type="submit"
        disabled={submitting}
        className="btn-primary w-full"
      >
        {submitting ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            {t('form.analyzing')}
          </>
        ) : (
          t('form.submit')
        )}
      </button>
    </div>
  )
}
