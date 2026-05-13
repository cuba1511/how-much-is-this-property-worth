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
      <HeroSection />

      <div
        id="form-area"
        className="mt-xl mx-xl pb-3xl"
      >
        {!data && (
          <>
            {apiError && (
              <div className="mb-md rounded-xl border border-destructive/30 bg-destructive/5 px-md py-sm text-sm text-destructive">
                {apiError}
              </div>
            )}
            <ValuationForm onResult={handleResult} onError={setApiError} />
          </>
        )}
      </div>

      {data && (
        <>
          <div id="results" className="mx-xl mt-xl mb-3xl">
            <ValuationResults
              result={data.result}
              request={data.request}
              lead={data.lead}
              onReset={handleReset}
            />
          </div>
          <FloatingChat leadName={data.lead?.fullName} />
        </>
      )}
    </>
  )
}

export default App
