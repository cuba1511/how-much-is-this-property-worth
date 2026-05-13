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
      <label className="text-sm font-medium text-ink">{t('address.label')}</label>
      <AddressSearch onSelect={handleAddressSelect} disabled={submitting} />
      {errors.address && (
        <p className="text-xs text-destructive">
          {errors.address.message === 'Required'
            ? t('address.error')
            : errors.address.message}
        </p>
      )}
      <div className="bg-surface-tint rounded-2xl shadow-card overflow-hidden mt-xs">
        <MapView position={mapPosition} height="300px" />
      </div>
    </div>
  )
}
