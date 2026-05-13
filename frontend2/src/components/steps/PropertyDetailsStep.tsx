import { Controller, useFormContext } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Home, Loader2, Sparkles, Hammer } from 'lucide-react'
import { Stepper } from '@/components/Stepper'
import type { ValuationRequestForm, PropertyCondition } from '@/lib/schemas'

const CONDITIONS: { value: PropertyCondition; labelKey: string; icon: typeof Sparkles }[] = [
  { value: 'obra_nueva', labelKey: 'condition.newBuild', icon: Sparkles },
  { value: 'buen_estado', labelKey: 'condition.good', icon: Home },
  { value: 'a_reformar', labelKey: 'condition.toRenovate', icon: Hammer },
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
      <div className="flex flex-col gap-sm">
        <label className="text-sm font-medium text-ink">{t('condition.label')}</label>
        <div className="grid grid-cols-3 gap-sm">
          {CONDITIONS.map(({ value, labelKey, icon: Icon }) => {
            const active = selectedCondition === value
            return (
              <button
                key={value}
                type="button"
                disabled={submitting}
                onClick={() => setValue('propertyCondition', value, { shouldValidate: true })}
                className={`flex flex-col items-center gap-xs rounded-xl border-2 px-sm py-md transition-all disabled:cursor-not-allowed disabled:opacity-60 ${
                  active
                    ? 'border-primary bg-primary/5 shadow-card'
                    : 'border-line bg-surface hover:border-primary/40 hover:bg-surface-tint'
                }`}
              >
                <Icon
                  className={`h-5 w-5 ${active ? 'text-primary' : 'text-ink-muted'}`}
                />
                <span
                  className={`text-xs font-semibold text-center ${
                    active ? 'text-primary' : 'text-ink-secondary'
                  }`}
                >
                  {t(labelKey)}
                </span>
              </button>
            )
          })}
        </div>
        {errors.propertyCondition && (
          <p className="text-xs text-destructive">{t('condition.error')}</p>
        )}
      </div>

      {/* m² */}
      <div className="flex flex-col gap-xs">
        <label htmlFor="m2" className="text-sm font-medium text-ink">
          {t('details.area')}
        </label>
        <Controller
          name="m2"
          control={control}
          render={({ field }) => (
            <div
              className={`flex items-center gap-sm rounded-xl border bg-surface px-md py-sm transition-all ${
                errors.m2
                  ? 'border-destructive'
                  : 'border-line focus-within:border-primary focus-within:ring-1 focus-within:ring-primary/20'
              }`}
            >
              <Home className="h-4 w-4 shrink-0 text-ink-muted" />
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
                className="w-full bg-transparent text-sm text-ink outline-none placeholder:text-ink-muted disabled:cursor-not-allowed"
                aria-describedby={errors.m2 ? 'm2-error' : undefined}
              />
            </div>
          )}
        />
        {errors.m2 && (
          <p id="m2-error" className="text-xs text-destructive">
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
        className="btn-primary w-full disabled:cursor-not-allowed disabled:opacity-60"
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
