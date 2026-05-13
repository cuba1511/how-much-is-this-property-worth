import { useFormContext } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Home, Building2, Waves, Sun, ArrowUp, Car, type LucideIcon } from 'lucide-react'
import type { ValuationRequestForm, PropertyType, FeatureKey } from '@/lib/schemas'

const PROPERTY_TYPES: { value: PropertyType; labelKey: string; icon: LucideIcon }[] = [
  { value: 'casa', labelKey: 'propertyType.house', icon: Home },
  { value: 'piso', labelKey: 'propertyType.apartment', icon: Building2 },
]

const FEATURES: { key: FeatureKey; labelKey: string; icon: LucideIcon }[] = [
  { key: 'pool', labelKey: 'features.pool', icon: Waves },
  { key: 'terrace', labelKey: 'features.terrace', icon: Sun },
  { key: 'elevator', labelKey: 'features.elevator', icon: ArrowUp },
  { key: 'parking', labelKey: 'features.parking', icon: Car },
]

interface PropertyTypeStepProps {
  submitting?: boolean
}

export function PropertyTypeStep({ submitting = false }: PropertyTypeStepProps) {
  const { t } = useTranslation()
  const { watch, setValue, formState: { errors } } = useFormContext<ValuationRequestForm>()
  const selectedType = watch('propertyType')
  const features = watch('features')

  function toggleFeature(key: FeatureKey) {
    if (submitting) return
    setValue(`features.${key}`, !features[key])
  }

  return (
    <div className="flex flex-col gap-lg">
      {/* Property type toggle */}
      <fieldset className="flex flex-col gap-sm">
        <legend className="text-text-md font-medium text-ink">{t('propertyType.label')}</legend>
        <div className="grid grid-cols-2 gap-md">
          {PROPERTY_TYPES.map(({ value, labelKey, icon: Icon }) => {
            const active = selectedType === value
            return (
              <button
                key={value}
                type="button"
                disabled={submitting}
                onClick={() => setValue('propertyType', value, { shouldValidate: true })}
                aria-pressed={active}
                className={[
                  'group flex flex-col items-center justify-center gap-sm rounded-lg border-2 px-md py-lg transition-all',
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
                    'h-10 w-10 transition-all group-hover:scale-110',
                    active ? 'text-brand' : 'text-ink-secondary',
                  ].join(' ')}
                />
                <span
                  className={[
                    'text-text-md font-semibold transition-colors',
                    active ? 'text-brand' : 'text-ink',
                  ].join(' ')}
                >
                  {t(labelKey)}
                </span>
              </button>
            )
          })}
        </div>
        {errors.propertyType && (
          <p className="text-text-sm text-destructive">{t('propertyType.error')}</p>
        )}
      </fieldset>

      {/* Feature cards */}
      <fieldset className="flex flex-col gap-sm">
        <legend className="text-text-md font-medium text-ink">{t('features.label')}</legend>
        <div className="grid grid-cols-1 gap-md sm:grid-cols-2">
          {FEATURES.map(({ key, labelKey, icon: Icon }) => {
            const checked = features?.[key] ?? false
            return (
              <button
                key={key}
                type="button"
                disabled={submitting}
                onClick={() => toggleFeature(key)}
                aria-pressed={checked}
                className={[
                  'flex items-center gap-sm rounded-lg border-2 px-md py-sm transition-all',
                  'disabled:cursor-not-allowed disabled:opacity-60',
                  checked
                    ? 'border-line-brand bg-primary/5'
                    : 'border-line bg-card hover:border-line-brand/40',
                ].join(' ')}
              >
                <span
                  className={[
                    'flex h-6 w-6 shrink-0 items-center justify-center rounded-xs border transition-all',
                    checked
                      ? 'border-line-brand bg-primary'
                      : 'border-line bg-card',
                  ].join(' ')}
                  aria-hidden
                >
                  {checked && (
                    <svg className="h-3.5 w-3.5 text-primary-foreground" viewBox="0 0 12 12" fill="none">
                      <path
                        d="M2.5 6L5 8.5L9.5 3.5"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  )}
                </span>
                <Icon
                  aria-hidden
                  strokeWidth={1.5}
                  className={[
                    'h-5 w-5 shrink-0',
                    checked ? 'text-brand' : 'text-ink-secondary',
                  ].join(' ')}
                />
                <span
                  className={[
                    'text-text-md font-semibold',
                    checked ? 'text-ink' : 'text-ink-secondary',
                  ].join(' ')}
                >
                  {t(labelKey)}
                </span>
              </button>
            )
          })}
        </div>
      </fieldset>
    </div>
  )
}
