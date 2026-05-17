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
  defaultAddress?: ResolvedAddress | null
}

export function AddressStep({
  onResolvedAddress,
  resolvedAddress,
  submitting = false,
  defaultAddress,
}: AddressStepProps) {
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
      <label className="text-sm font-medium text-ink">{t('address.label')}</label>
      <AddressSearch
        onSelect={handleAddressSelect}
        disabled={submitting}
        defaultAddress={defaultAddress ?? resolvedAddress}
      />
      {errors.address && (
        <p className="text-xs text-destructive">
          {errors.address.message === 'Required'
            ? t('address.error')
            : errors.address.message}
        </p>
      )}
      <div className="mt-xs overflow-hidden rounded-2xl border border-line">
        <MapView position={mapPosition} height="300px" />
      </div>
    </div>
  )
}
