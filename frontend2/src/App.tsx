import { Home } from 'lucide-react'
import { HeroSection } from '@/components/HeroSection'

function App() {
  return (
    <>
      <HeroSection />
      <div
        id="form-area"
        className="bg-surface-tint rounded-2xl shadow-card p-2xl min-h-[200px] mt-xl mx-md md:mx-xl mb-3xl flex flex-col items-center justify-center gap-4"
      >
        <Home size={48} className="text-ink-muted opacity-50" />
        <h2 className="text-ink-muted font-medium">
          Aquí aparecerá el formulario de valoración
        </h2>
        <p className="text-ink-muted text-sm max-w-md text-center">
          Completa los datos de tu propiedad para obtener una estimación basada en comparables del mercado.
        </p>
      </div>
    </>
  )
}

export default App
