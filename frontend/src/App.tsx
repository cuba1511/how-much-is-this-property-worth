import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, MailCheck } from 'lucide-react'
import { Navbar } from '@/components/Navbar'
import { HeroSection } from '@/components/HeroSection'
import { ValuationForm } from '@/components/ValuationForm'
import { ValuationResults } from '@/components/ValuationResults'
import { FloatingChat } from '@/components/FloatingChat'
import type {
  LeadInfo,
  LeadResponse,
  ResolvedAddress,
  ValuationRequest,
  ValuationResponse,
} from '@/lib/types'

interface ValuationData {
  result: ValuationResponse
  request: ValuationRequest
  lead?: LeadInfo
}

interface PendingLead {
  lead: LeadInfo
  response: LeadResponse
}

function App() {
  const [data, setData] = useState<ValuationData | null>(null)
  const [pending, setPending] = useState<PendingLead | null>(null)
  const [apiError, setApiError] = useState<string | null>(null)
  const [started, setStarted] = useState(false)
  const [prefillAddress, setPrefillAddress] = useState<ResolvedAddress | null>(null)

  function handleResult(result: ValuationResponse, request: ValuationRequest, lead?: LeadInfo) {
    setApiError(null)
    setPending(null)
    setData({ result, request, lead })
    setTimeout(() => {
      document.getElementById('results')?.scrollIntoView({ behavior: 'smooth' })
    }, 100)
  }

  function handlePending(lead: LeadInfo, response: LeadResponse) {
    setApiError(null)
    setData(null)
    setPending({ lead, response })
    setTimeout(() => {
      document.getElementById('pending')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 100)
  }

  function handleReset() {
    setData(null)
    setPending(null)
    setApiError(null)
    setStarted(false)
    setPrefillAddress(null)
    setTimeout(() => {
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }, 100)
  }

  function handleStart(address: ResolvedAddress) {
    setPrefillAddress(address)
    setStarted(true)
    setTimeout(() => {
      document.getElementById('form-area')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 50)
  }

  return (
    <>
      <Navbar />

      <main className="flex-1 w-full">
        {!data && !pending && !started && <HeroSection onStart={handleStart} />}

        {!data && !pending && started && (
          <section
            id="form-area"
            className="px-md md:px-xl pt-xl pb-3xl"
          >
            <div className="mx-auto w-full max-w-2xl">
              {apiError && (
                <div
                  role="alert"
                  className="mb-md rounded-xl border border-destructive/30 bg-destructive/5 px-md py-sm text-sm text-destructive"
                >
                  {apiError}
                </div>
              )}
              <div className="card-surface p-lg md:p-xl">
                <ValuationForm
                  onResult={handleResult}
                  onPending={handlePending}
                  onError={setApiError}
                  initialResolvedAddress={prefillAddress}
                />
              </div>
            </div>
          </section>
        )}

        {pending && (
          <PendingValuationScreen pending={pending} onReset={handleReset} />
        )}

        {data && (
          <section
            id="results"
            className="px-md md:px-xl pt-xl pb-3xl"
          >
            <div className="mx-auto w-full max-w-5xl">
              <ValuationResults
                result={data.result}
                request={data.request}
                lead={data.lead}
                onReset={handleReset}
              />
            </div>
          </section>
        )}
      </main>

      {data && <FloatingChat leadName={data.lead?.full_name} />}
    </>
  )
}

interface PendingValuationScreenProps {
  pending: PendingLead
  onReset: () => void
}

function PendingValuationScreen({ pending, onReset }: PendingValuationScreenProps) {
  const { t } = useTranslation()
  const { lead, response } = pending

  return (
    <section id="pending" className="px-md md:px-xl pt-xl pb-3xl">
      <div className="mx-auto w-full max-w-2xl">
        <div className="card-surface p-lg md:p-xl flex flex-col items-center gap-md text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
            <Check className="h-7 w-7 text-primary" />
          </div>
          <h2 className="text-2xl font-semibold tracking-tight text-ink">
            {t('form.pending.title')}
          </h2>
          <p className="max-w-md text-sm text-ink-secondary">
            {response.message ?? t('form.pending.description')}
          </p>
          <div className="flex items-center gap-sm rounded-xl border border-emerald-200 bg-emerald-50 px-md py-sm">
            <MailCheck className="h-4 w-4 shrink-0 text-emerald-600" />
            <p className="text-sm text-emerald-800">
              {t('form.pending.emailHint', { email: lead.email })}
            </p>
          </div>
          <button type="button" className="btn-secondary" onClick={onReset}>
            {t('form.pending.reset')}
          </button>
        </div>
      </div>
    </section>
  )
}

export default App
