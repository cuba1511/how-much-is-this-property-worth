import { useFormContext } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import {
  Home,
  Building2,
  Waves,
  Sun,
  ArrowUpFromDot,
  Car,
} from 'lucide-react'
import type { ValuationRequestForm, PropertyType, FeatureKey } from '@/lib/schemas'

const PROPERTY_TYPES: { value: PropertyType; labelKey: string; icon: typeof Home }[] = [
  { value: 'casa', labelKey: 'propertyType.house', icon: Home },
  { value: 'piso', labelKey: 'propertyType.apartment', icon: Building2 },
]

const FEATURES: { key: FeatureKey; labelKey: string; icon: typeof Waves }[] = [
  { key: 'pool', labelKey: 'features.pool', icon: Waves },
  { key: 'terrace', labelKey: 'features.terrace', icon: Sun },
  { key: 'elevator', labelKey: 'features.elevator', icon: ArrowUpFromDot },
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
      <div className="flex flex-col gap-sm">
        <label className="text-sm font-medium text-ink">{t('propertyType.label')}</label>
        <div className="grid grid-cols-2 gap-md">
          {PROPERTY_TYPES.map(({ value, labelKey, icon: Icon }) => {
            const active = selectedType === value
            return (
              <button
                key={value}
                type="button"
                disabled={submitting}
                onClick={() => setValue('propertyType', value, { shouldValidate: true })}
                className={`flex flex-col items-center justify-center gap-sm rounded-2xl border-2 px-md py-lg transition-all disabled:cursor-not-allowed disabled:opacity-60 ${
                  active
                    ? 'border-primary bg-primary/5 shadow-card'
                    : 'border-line bg-surface hover:border-primary/40 hover:bg-surface-tint'
                }`}
              >
                <Icon
                  className={`h-8 w-8 transition-colors ${
                    active ? 'text-primary' : 'text-ink-muted'
                  }`}
                />
                <span
                  className={`text-sm font-semibold transition-colors ${
                    active ? 'text-primary' : 'text-ink'
                  }`}
                >
                  {t(labelKey)}
                </span>
              </button>
            )
          })}
        </div>
        {errors.propertyType && (
          <p className="text-xs text-destructive">{t('propertyType.error')}</p>
        )}
      </div>

      {/* Feature cards */}
      <div className="flex flex-col gap-sm">
        <label className="text-sm font-medium text-ink">{t('features.label')}</label>
        <div className="grid grid-cols-2 gap-md">
          {FEATURES.map(({ key, labelKey, icon: Icon }) => {
            const checked = features?.[key] ?? false
            return (
              <button
                key={key}
                type="button"
                disabled={submitting}
                onClick={() => toggleFeature(key)}
                className={`flex items-center gap-sm rounded-xl border-2 px-md py-md transition-all disabled:cursor-not-allowed disabled:opacity-60 ${
                  checked
                    ? 'border-primary bg-primary/5'
                    : 'border-line bg-surface hover:border-primary/40'
                }`}
              >
                <div
                  className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md border transition-all ${
                    checked
                      ? 'border-primary bg-primary'
                      : 'border-ink-muted bg-surface'
                  }`}
                >
                  {checked && (
                    <svg className="h-3.5 w-3.5 text-white" viewBox="0 0 12 12" fill="none">
                      <path
                        d="M2.5 6L5 8.5L9.5 3.5"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  )}
                </div>
                <Icon
                  className={`h-5 w-5 shrink-0 ${checked ? 'text-primary' : 'text-ink-muted'}`}
                />
                <span
                  className={`text-sm font-semibold ${checked ? 'text-ink' : 'text-ink-secondary'}`}
                >
                  {t(labelKey)}
                </span>
              </button>
            )
          })}
        </div>
      </div>

    </div>
  )
}
