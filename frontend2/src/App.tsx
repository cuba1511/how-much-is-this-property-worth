import { useState } from 'react'
import { Navbar } from '@/components/Navbar'
import { HeroSection } from '@/components/HeroSection'
import { ValuationForm } from '@/components/ValuationForm'
import { ValuationResults } from '@/components/ValuationResults'
import type { ValuationResponse } from '@/lib/types'

function App() {
  const [result, setResult] = useState<ValuationResponse | null>(null)
  const [apiError, setApiError] = useState<string | null>(null)

  function handleResult(res: ValuationResponse) {
    setApiError(null)
    setResult(res)
    setTimeout(() => {
      document.getElementById('results')?.scrollIntoView({ behavior: 'smooth' })
    }, 100)
  }

  function handleReset() {
    setResult(null)
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
        {!result && (
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

      {result && (
        <div id="results" className="mx-xl mt-xl mb-3xl">
          <ValuationResults result={result} onReset={handleReset} />
        </div>
      )}
    </>
  )
}

export default App
