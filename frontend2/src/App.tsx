import { useState } from 'react'
import { Navbar } from '@/components/Navbar'
import { HeroSection } from '@/components/HeroSection'
import { ValuationForm } from '@/components/ValuationForm'
import { ValuationResults } from '@/components/ValuationResults'
import { FloatingChat } from '@/components/FloatingChat'
import type { ValuationResponse, ValuationRequest, LeadInfo } from '@/lib/types'

interface ValuationData {
  result: ValuationResponse
  request: ValuationRequest
  lead?: LeadInfo
}

function App() {
  const [data, setData] = useState<ValuationData | null>(null)
  const [apiError, setApiError] = useState<string | null>(null)

  function handleResult(result: ValuationResponse, request: ValuationRequest, lead?: LeadInfo) {
    setApiError(null)
    setData({ result, request, lead })
    setTimeout(() => {
      document.getElementById('results')?.scrollIntoView({ behavior: 'smooth' })
    }, 100)
  }

  function handleReset() {
    setData(null)
    setApiError(null)
    setTimeout(() => {
      document.getElementById('form-area')?.scrollIntoView({ behavior: 'smooth' })
    }, 100)
  }

  return (
    <>
      <Navbar />

      <main className="flex-1 w-full">
        {!data && (
          <>
            <HeroSection />

            <section
              id="form-area"
              className="px-md md:px-xl pb-3xl"
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
                  <ValuationForm onResult={handleResult} onError={setApiError} />
                </div>
              </div>
            </section>
          </>
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

      {data && <FloatingChat leadName={data.lead?.fullName} />}
    </>
  )
}

export default App
