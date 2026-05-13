import { useState } from 'react'
import { Navbar } from '@/components/Navbar'
import { LandingHero } from '@/components/LandingHero'
import { ValuationForm } from '@/components/ValuationForm'
import { ValuationResults } from '@/components/ValuationResults'
import type { ValuationResponse, ValuationRequest, LeadInfo } from '@/lib/types'

type View = 'landing' | 'form' | 'results'

interface ValuationData {
  result: ValuationResponse
  request: ValuationRequest
  lead?: LeadInfo
}

function App() {
  const [view, setView] = useState<View>('landing')
  const [data, setData] = useState<ValuationData | null>(null)
  const [apiError, setApiError] = useState<string | null>(null)

  function startForm() {
    setApiError(null)
    setView('form')
    requestAnimationFrame(() => {
      window.scrollTo({ top: 0, behavior: 'smooth' })
    })
  }

  function handleResult(result: ValuationResponse, request: ValuationRequest, lead?: LeadInfo) {
    setApiError(null)
    setData({ result, request, lead })
    setView('results')
    requestAnimationFrame(() => {
      window.scrollTo({ top: 0, behavior: 'smooth' })
    })
  }

  function handleReset() {
    setData(null)
    setApiError(null)
    setView('landing')
    requestAnimationFrame(() => {
      window.scrollTo({ top: 0, behavior: 'smooth' })
    })
  }

  return (
    <>
      <Navbar onHome={view !== 'landing' ? handleReset : undefined} />

      <main className="flex-1">
        {view === 'landing' && <LandingHero onStart={startForm} />}

        {view === 'form' && (
          <section id="form-area" className="container mx-auto py-2xl md:py-3xl">
            <div className="relative mx-auto w-full max-w-3xl">
              <div
                aria-hidden
                className="pointer-events-none absolute -inset-md -z-10 rounded-card bg-gradient-to-br from-primary/10 via-transparent to-primary/5 blur-3xl"
              />
              {apiError && (
                <div className="alert-error mb-md rounded-lg border border-line-error px-md py-sm text-text-md">
                  {apiError}
                </div>
              )}
              <ValuationForm
                onResult={handleResult}
                onError={setApiError}
                onBackToLanding={handleReset}
              />
            </div>
          </section>
        )}

        {view === 'results' && data && (
          <section id="results" className="container mx-auto py-xl md:py-2xl">
            <ValuationResults
              result={data.result}
              request={data.request}
              lead={data.lead}
              onReset={handleReset}
            />
          </section>
        )}
      </main>
    </>
  )
}

export default App
