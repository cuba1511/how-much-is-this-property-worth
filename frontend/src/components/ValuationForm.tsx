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
  type LucideIcon,
} from 'lucide-react'
import { StepIndicator } from '@/components/StepIndicator'
import { SelectedAddressBanner } from '@/components/SelectedAddressBanner'
import { PropertyIdentificationStep } from '@/components/steps/PropertyIdentificationStep'
import { PropertyTypeStep } from '@/components/steps/PropertyTypeStep'
import { PropertyDetailsStep } from '@/components/steps/PropertyDetailsStep'
import { LeadDialog, type LeadData } from '@/components/LeadDialog'
import {
  valuationRequestSchema,
  step1Schema,
  step2Schema,
  step3Schema,
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
]

interface ValuationFormProps {
  onResult: (result: ValuationResponse, request: ValuationRequest, lead?: LeadInfo) => void
  onError: (message: string) => void
}

export function ValuationForm({ onResult, onError }: ValuationFormProps) {
  const { t } = useTranslation()
  const [currentStep, setCurrentStep] = useState(0)
  const [resolvedAddress, setResolvedAddress] = useState<ResolvedAddress | null>(null)
  const [selectedUnit, setSelectedUnit] = useState<CadastralUnit | null>(null)
  const [cadastralUnitsCount, setCadastralUnitsCount] = useState(0)
  const [submitting, setSubmitting] = useState(false)
  const [leadDialogOpen, setLeadDialogOpen] = useState(false)
  const [unitError, setUnitError] = useState<string | null>(null)

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

  const showAddressBanner = Boolean(resolvedAddress) && currentStep > 0

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
    const valid = await validateCurrentStep()
    if (!valid) return
    setLeadDialogOpen(true)
  }

  async function handleLeadSubmit(formLead: LeadData) {
    setSubmitting(true)
    try {
      const data = methods.getValues()
      const { propertyType, features, propertyCondition, ...apiFields } = data
      const valuationRequest: ValuationRequest = {
        ...apiFields,
        property_type: propertyType,
        property_condition: propertyCondition,
        features,
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
      setLeadDialogOpen(false)
      onResult(result.valuation, valuationRequest, wireLead)
    } catch (err) {
      const code = err instanceof ValuationError ? err.code : 'server'
      onError(t(`form.error.${code}`))
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

        {showAddressBanner && resolvedAddress && (
          <SelectedAddressBanner address={resolvedAddress} unit={selectedUnit} />
        )}

        <div className="min-h-[280px]">
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
          {currentStep === 2 && (
            <PropertyDetailsStep submitting={submitting} showSubmit />
          )}
        </div>

        {STEPS[currentStep].impacts.length > 0 && (
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

        <div className="mt-xs flex items-center justify-between gap-sm">
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
            <span />
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
