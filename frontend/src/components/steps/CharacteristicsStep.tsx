import { PropertyTypeStep } from '@/components/steps/PropertyTypeStep'
import { PropertyDetailsStep } from '@/components/steps/PropertyDetailsStep'

interface CharacteristicsStepProps {
  submitting: boolean
}

export function CharacteristicsStep({ submitting }: CharacteristicsStepProps) {
  return (
    <div className="flex flex-col gap-xl">
      <PropertyTypeStep submitting={submitting} />
      <PropertyDetailsStep submitting={submitting} />
    </div>
  )
}
