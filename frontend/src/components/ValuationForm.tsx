import { useState } from 'react'
import { useForm, FormProvider } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { zodResolver } from '@hookform/resolvers/zod'
import {
  ChevronLeft,
  ChevronRight,
  MapPin,
  BarChart3,
  Home,
  Ruler,
  Target,
  type LucideIcon,
} from 'lucide-react'
import { StepIndicator } from '@/components/StepIndicator'
import { SelectedAddressBanner } from '@/components/SelectedAddressBanner'
import { PropertyIdentificationStep } from '@/components/steps/PropertyIdentificationStep'
import { PropertyTypeStep } from '@/components/steps/PropertyTypeStep'
import { PropertyDetailsStep } from '@/components/steps/PropertyDetailsStep'
import { ValuationIntentStep } from '@/components/steps/ValuationIntentStep'
import { LeadDialog, type LeadData } from '@/components/LeadDialog'
import {
  valuationRequestSchema,
  step1Schema,
  step2Schema,
  step3Schema,
  step4Schema,
  type ValuationRequestForm,
} from '@/lib/schemas'
import { submitLead, ValuationError } from '@/lib/api'
import type {
  CadastralUnit,
  LeadInfo,
  ResolvedAddress,
  ValuationRequest,
  ValuationResponse,
} from '@/lib/types'

interface ImpactItem { icon: LucideIcon; key: string }

interface StepConfig { labelKey: string; impacts: ImpactItem[] }

const STEPS: StepConfig[] = [
  {
    labelKey: 'steps.identification',
    impacts: [
      { icon: MapPin, key: 'impacts.locationValue' },
      { icon: BarChart3, key: 'impacts.realTimePrices' },
    ],
  },
  {
    labelKey: 'steps.characteristics',
    impacts: [{ icon: Home, key: 'impacts.precisionMatters' }],
  },
  {
    labelKey: 'steps.details',
    impacts: [{ icon: Ruler, key: 'impacts.resultTime' }],
  },
  {
    labelKey: 'steps.purpose',
    impacts: [{ icon: Target, key: 'impacts.precisionMatters' }],
  },
]

interface ValuationFormProps {
  onResult: (result: ValuationResponse, request: ValuationRequest, lead?: LeadInfo) => void
  onError: (message: string) => void
  initialResolvedAddress?: ResolvedAddress | null
}

export function ValuationForm({ onResult, onError, initialResolvedAddress = null }: ValuationFormProps) {
  const { t } = useTranslation()
  const [currentStep, setCurrentStep] = useState(0)
  const [maxStepReached, setMaxStepReached] = useState(0)
  const [resolvedAddress, setResolvedAddress] = useState<ResolvedAddress | null>(
    initialResolvedAddress,
  )
  const [selectedUnit, setSelectedUnit] = useState<CadastralUnit | null>(null)
  const [cadastralUnitsCount, setCadastralUnitsCount] = useState(0)
  const [submitting, setSubmitting] = useState(false)
  const [unitError, setUnitError] = useState<string | null>(null)
  const [leadDialogOpen, setLeadDialogOpen] = useState(false)

  const methods = useForm<ValuationRequestForm>({
    resolver: zodResolver(valuationRequestSchema),
    defaultValues: {
      propertyType: undefined as unknown as ValuationRequestForm['propertyType'],
      features: { pool: false, terrace: false, elevator: false, parking: false },
      address: initialResolvedAddress?.label ?? '',
      propertyCondition: undefined as unknown as ValuationRequestForm['propertyCondition'],
      m2: undefined as unknown as number,
      bedrooms: 0,
      bathrooms: 1,
      valuationIntent: undefined as unknown as ValuationRequestForm['valuationIntent'],
      sellReason: undefined,
      sellTimeline: undefined,
      rentTimeline: undefined,
    },
    mode: 'onTouched',
  })

  const showAddressBanner = Boolean(resolvedAddress) && currentStep > 0
  const isLastStep = currentStep === STEPS.length - 1

  function setIssueErrors(issues: { path: PropertyKey[]; message: string }[]) {
    for (const issue of issues) {
      const field = String(issue.path[0]) as keyof ValuationRequestForm
      if (field) methods.setError(field, { message: issue.message })
    }
  }

  async function validateCurrentStep(): Promise<boolean> {
    const values = methods.getValues()
    setUnitError(null)

    if (currentStep === 0) {
      const r = step1Schema.safeParse({ address: values.address })
      if (!r.success) {
        setIssueErrors(r.error.issues)
        return false
      }
      if (!resolvedAddress?.house_number) {
        setUnitError(t('catastro.needStreetNumber'))
        return false
      }
      if (cadastralUnitsCount > 1 && !selectedUnit) {
        setUnitError(t('catastro.selectUnitError'))
        return false
      }
      return true
    }

    if (currentStep === 1) {
      const r = step2Schema.safeParse({
        propertyType: values.propertyType,
        features: values.features,
      })
      if (!r.success) {
        setIssueErrors(r.error.issues)
        return false
      }
      return true
    }

    if (currentStep === 2) {
      const r = step3Schema.safeParse({
        propertyCondition: values.propertyCondition,
        m2: values.m2,
        bedrooms: values.bedrooms,
        bathrooms: values.bathrooms,
      })
      if (!r.success) {
        setIssueErrors(r.error.issues)
        return false
      }
      return true
    }

    if (currentStep === 3) {
      const r = step4Schema.safeParse({
        valuationIntent: values.valuationIntent,
        sellReason: values.sellReason,
        sellTimeline: values.sellTimeline,
        rentTimeline: values.rentTimeline,
      })
      if (!r.success) {
        setIssueErrors(r.error.issues)
        return false
      }
      return true
    }

    return true
  }

  async function handleNext() {
    const valid = await validateCurrentStep()
    if (valid && currentStep < STEPS.length - 1) {
      const next = currentStep + 1
      setCurrentStep(next)
      setMaxStepReached((m) => Math.max(m, next))
    }
  }

  function handleBack() {
    if (currentStep > 0 && !submitting) setCurrentStep((s) => s - 1)
  }

  async function handleRequestValuation() {
    const valid = await validateCurrentStep()
    if (valid) setLeadDialogOpen(true)
  }

  async function handleLeadSubmit(formLead: LeadData) {
    setSubmitting(true)
    try {
      const data = methods.getValues()
      const {
        propertyType,
        features,
        propertyCondition,
        valuationIntent,
        sellReason,
        sellTimeline,
        rentTimeline,
        ...apiFields
      } = data
      const valuationRequest: ValuationRequest = {
        ...apiFields,
        property_type: propertyType,
        property_condition: propertyCondition,
        features,
        valuation_intent: valuationIntent,
        sell_reason: sellReason,
        sell_timeline: sellTimeline,
        rent_timeline: rentTimeline,
        selected_address: resolvedAddress ?? undefined,
        selected_cadastral_unit: selectedUnit ?? undefined,
      }
      const wireLead: LeadInfo = {
        full_name: formLead.fullName,
        email: formLead.email,
        phone: formLead.phone,
      }
      const result = await submitLead({
        lead: wireLead,
        valuation_request: valuationRequest,
      })
      onResult(result.valuation, valuationRequest, wireLead)
    } catch (err) {
      const code = err instanceof ValuationError ? err.code : 'server'
      onError(t(`form.error.${code}`))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <FormProvider {...methods}>
      <div className="flex flex-col gap-lg">
        <StepIndicator
          steps={STEPS.map((s) => ({ label: t(s.labelKey) }))}
          current={currentStep}
          maxReached={maxStepReached}
        />

        {showAddressBanner && resolvedAddress && (
          <SelectedAddressBanner address={resolvedAddress} unit={selectedUnit} />
        )}

        <div className="min-h-[240px]">
          {currentStep === 0 && (
            <>
              <PropertyIdentificationStep
                resolvedAddress={resolvedAddress}
                onResolvedAddress={setResolvedAddress}
                selectedUnit={selectedUnit}
                onSelectedUnit={(unit) => {
                  setSelectedUnit(unit)
                  setUnitError(null)
                }}
                onUnitsCountChange={setCadastralUnitsCount}
                submitting={submitting}
              />
              {unitError && (
                <p className="mt-sm text-xs text-destructive">{unitError}</p>
              )}
            </>
          )}
          {currentStep === 1 && <PropertyTypeStep submitting={submitting} />}
          {currentStep === 2 && <PropertyDetailsStep submitting={submitting} showSubmit={false} />}
          {currentStep === 3 && <ValuationIntentStep submitting={submitting} />}
        </div>

        <LeadDialog
          open={leadDialogOpen}
          onOpenChange={setLeadDialogOpen}
          onSubmit={handleLeadSubmit}
          submitting={submitting}
        />

        {STEPS[currentStep].impacts.length > 0 && !submitting && (
          <aside
            aria-label={t(STEPS[currentStep].labelKey)}
            className="flex flex-col gap-sm rounded-2xl border border-primary/15 bg-primary/5 px-md py-md"
          >
            {STEPS[currentStep].impacts.map(({ icon: Icon, key }, i) => (
              <div key={i} className="flex items-center gap-sm">
                <Icon className="h-4 w-4 shrink-0 text-primary" />
                <p className="text-xs font-medium leading-relaxed text-ink-secondary">{t(key)}</p>
              </div>
            ))}
          </aside>
        )}

        {!submitting && (
          <div className="mt-xs flex items-center justify-between gap-sm">
            {currentStep > 0 ? (
              <button
                type="button"
                onClick={handleBack}
                className="btn-ghost"
              >
                <ChevronLeft className="h-4 w-4" />
                {t('form.back')}
              </button>
            ) : (
              <span />
            )}

            {isLastStep ? (
              <button
                type="button"
                onClick={() => void handleRequestValuation()}
                className="btn-primary"
              >
                {t('lead.submit')}
                <ChevronRight className="h-4 w-4" />
              </button>
            ) : (
              <button type="button" onClick={handleNext} className="btn-primary">
                {t('form.next')}
                <ChevronRight className="h-4 w-4" />
              </button>
            )}
          </div>
        )}
      </div>
    </FormProvider>
  )
}
