import { useFormContext } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { AddressSearch } from '@/components/AddressSearch'
import { MapView } from '@/components/MapView'
import type { ValuationRequestForm } from '@/lib/schemas'
import type { ResolvedAddress } from '@/lib/types'

interface AddressStepProps {
  onResolvedAddress: (addr: ResolvedAddress | null) => void
  resolvedAddress: ResolvedAddress | null
  submitting?: boolean
}

export function AddressStep({ onResolvedAddress, resolvedAddress, submitting = false }: AddressStepProps) {
  const { t } = useTranslation()
  const { setValue, formState: { errors } } = useFormContext<ValuationRequestForm>()

  const mapPosition: [number, number] | null = resolvedAddress
    ? [resolvedAddress.lat, resolvedAddress.lon]
    : null

  function handleAddressSelect(addr: ResolvedAddress | null) {
    if (submitting) return
    onResolvedAddress(addr)
    setValue('address', addr?.label ?? '', { shouldValidate: true })
  }

  return (
    <div className="flex flex-col gap-sm">
      <label className="text-text-md font-medium text-ink">{t('address.label')}</label>
      <AddressSearch onSelect={handleAddressSelect} disabled={submitting} />
      {errors.address && (
        <p className="text-text-sm text-destructive">
          {errors.address.message === 'Required'
            ? t('address.error')
            : errors.address.message}
        </p>
      )}
      <div className="mt-xs overflow-hidden rounded-lg border border-line-subtle bg-surface-tint shadow-level-1">
        <MapView position={mapPosition} height="300px" />
      </div>
    </div>
  )
}
