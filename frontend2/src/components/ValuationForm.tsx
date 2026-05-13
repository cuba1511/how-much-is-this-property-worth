import { useState } from 'react'
import { useForm, FormProvider } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { zodResolver } from '@hookform/resolvers/zod'
import {
  ChevronLeft,
  ChevronRight,
  TrendingUp,
  Clock,
  MapPin,
  BarChart3,
  type LucideIcon,
} from 'lucide-react'
import { StepIndicator } from '@/components/StepIndicator'
import { PropertyTypeStep } from '@/components/steps/PropertyTypeStep'
import { AddressStep } from '@/components/steps/AddressStep'
import { PropertyDetailsStep } from '@/components/steps/PropertyDetailsStep'
import { LeadDialog, type LeadData } from '@/components/LeadDialog'
import {
  valuationRequestSchema,
  step1Schema,
  step2Schema,
  step3Schema,
  type ValuationRequestForm,
} from '@/lib/schemas'
import { valuateProperty } from '@/lib/api'
import type { ResolvedAddress, ValuationResponse } from '@/lib/types'

interface ImpactItem { icon: LucideIcon; key: string }

interface StepConfig { labelKey: string; impacts: ImpactItem[] }

const STEPS: StepConfig[] = [
  {
    labelKey: 'steps.property',
    impacts: [
      { icon: TrendingUp, key: 'impacts.propertiesSold' },
      { icon: Clock, key: 'impacts.avgSaleTime' },
    ],
  },
  {
    labelKey: 'steps.location',
    impacts: [
      { icon: MapPin, key: 'impacts.locationValue' },
      { icon: BarChart3, key: 'impacts.realTimePrices' },
    ],
  },
  {
    labelKey: 'steps.details',
    impacts: [],
  },
]

interface ValuationFormProps {
  onResult: (result: ValuationResponse) => void
  onError: (message: string) => void
}

export function ValuationForm({ onResult, onError }: ValuationFormProps) {
  const { t } = useTranslation()
  const [currentStep, setCurrentStep] = useState(0)
  const [resolvedAddress, setResolvedAddress] = useState<ResolvedAddress | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [leadDialogOpen, setLeadDialogOpen] = useState(false)

  const methods = useForm<ValuationRequestForm>({
    resolver: zodResolver(valuationRequestSchema),
    defaultValues: {
      propertyType: undefined as unknown as ValuationRequestForm['propertyType'],
      features: { pool: false, terrace: false, elevator: false, parking: false },
      address: '',
      propertyCondition: undefined as unknown as ValuationRequestForm['propertyCondition'],
      m2: undefined as unknown as number,
      bedrooms: 0,
      bathrooms: 1,
    },
    mode: 'onTouched',
  })

  function setIssueErrors(issues: { path: PropertyKey[]; message: string }[]) {
    for (const issue of issues) {
      const field = String(issue.path[0]) as keyof ValuationRequestForm
      if (field) methods.setError(field, { message: issue.message })
    }
  }

  async function validateCurrentStep(): Promise<boolean> {
    const values = methods.getValues()

    if (currentStep === 0) {
      const r = step1Schema.safeParse({ propertyType: values.propertyType, features: values.features })
      if (!r.success) { setIssueErrors(r.error.issues); return false }
    } else if (currentStep === 1) {
      const r = step2Schema.safeParse({ address: values.address })
      if (!r.success) { setIssueErrors(r.error.issues); return false }
    } else {
      const r = step3Schema.safeParse({
        propertyCondition: values.propertyCondition,
        m2: values.m2,
        bedrooms: values.bedrooms,
        bathrooms: values.bathrooms,
      })
      if (!r.success) { setIssueErrors(r.error.issues); return false }
    }
    return true
  }

  async function handleNext() {
    const valid = await validateCurrentStep()
    if (valid && currentStep < STEPS.length - 1) {
      setCurrentStep((s) => s + 1)
    }
  }

  function handleBack() {
    if (currentStep > 0) setCurrentStep((s) => s - 1)
  }

  async function onSubmit(_data: ValuationRequestForm) {
    setLeadDialogOpen(true)
  }

  async function handleLeadSubmit(lead: LeadData) {
    setSubmitting(true)
    try {
      const data = methods.getValues()
      const { propertyType, features, propertyCondition, ...apiFields } = data
      const result = await valuateProperty({
        ...apiFields,
        selected_address: resolvedAddress ?? undefined,
        lead,
      })
      setLeadDialogOpen(false)
      onResult(result)
    } catch (err) {
      onError(err instanceof Error ? err.message : t('form.serverError'))
      setLeadDialogOpen(false)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <FormProvider {...methods}>
      <form
        onSubmit={methods.handleSubmit(onSubmit)}
        noValidate
        className="flex flex-col gap-lg"
      >
        <StepIndicator steps={STEPS.map(s => ({ label: t(s.labelKey) }))} current={currentStep} />

        <div className="min-h-[320px]">
          {currentStep === 0 && <PropertyTypeStep submitting={submitting} />}
          {currentStep === 1 && (
            <AddressStep
              resolvedAddress={resolvedAddress}
              onResolvedAddress={setResolvedAddress}
              submitting={submitting}
            />
          )}
          {currentStep === 2 && <PropertyDetailsStep submitting={submitting} />}
        </div>

        {/* Impact phrases */}
        {STEPS[currentStep].impacts.length > 0 && (
          <div className="flex flex-col gap-sm rounded-2xl bg-primary/5 border border-primary/15 px-md py-md">
            {STEPS[currentStep].impacts.map(({ icon: Icon, key }, i) => (
              <div key={i} className="flex items-center gap-sm">
                <Icon className="h-4 w-4 shrink-0 text-primary" />
                <p className="text-xs font-medium text-ink-secondary leading-relaxed">{t(key)}</p>
              </div>
            ))}
          </div>
        )}

        {/* Navigation */}
        <div className="flex items-center justify-between pt-sm">
          {currentStep > 0 ? (
            <button
              type="button"
              onClick={handleBack}
              disabled={submitting}
              className="btn-ghost disabled:cursor-not-allowed disabled:opacity-40"
            >
              <ChevronLeft className="h-4 w-4" />
              {t('form.back')}
            </button>
          ) : (
            <div />
          )}

          {currentStep < STEPS.length - 1 && (
            <button
              type="button"
              onClick={handleNext}
              disabled={submitting}
              className="btn-primary disabled:cursor-not-allowed disabled:opacity-60"
            >
              {t('form.next')}
              <ChevronRight className="h-4 w-4" />
            </button>
          )}
        </div>
      </form>

      <LeadDialog
        open={leadDialogOpen}
        onOpenChange={setLeadDialogOpen}
        onSubmit={handleLeadSubmit}
        submitting={submitting}
      />
    </FormProvider>
  )
}
