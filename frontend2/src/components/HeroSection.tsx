export function HeroSection() {
  return (
    <section className="bg-surface pt-2xl pb-xl px-md md:px-xl">
      <h1>
        ¿Cuánto vale <span className="text-primary">tu casa</span>?
      </h1>
      <p className="text-ink-secondary max-w-[560px] mt-3">
        Introduce los datos de tu propiedad y te mostramos comparables reales para estimar su valor de mercado.
      </p>
      <a href="#form-area" className="btn-primary mt-6 inline-flex">
        Valorar mi propiedad
      </a>
    </section>
  )
}
