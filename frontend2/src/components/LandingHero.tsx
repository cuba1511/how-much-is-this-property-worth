import { useTranslation } from 'react-i18next'
import { ArrowRight, Clock, MapPin, BarChart3, type LucideIcon } from 'lucide-react'

export interface LandingHeroProps {
  onStart: () => void
}

const TRUST_CHIPS: { icon: LucideIcon; key: string }[] = [
  { icon: Clock,     key: 'impacts.resultTime' },
  { icon: MapPin,    key: 'impacts.realTimePrices' },
  { icon: BarChart3, key: 'impacts.propertiesSold' },
]

export function LandingHero({ onStart }: LandingHeroProps) {
  const { t } = useTranslation()

  return (
    <section className="relative overflow-hidden bg-page">
      {/* Subtle brand gradient backdrop */}
      <div
        aria-hidden
        className="absolute inset-0 -z-10 bg-gradient-to-b from-surface-tint/60 via-page to-page"
      />

      <div className="container mx-auto grid items-center gap-2xl py-xl md:py-2xl lg:min-h-[calc(100svh-4rem)] lg:grid-cols-[1fr_1fr] lg:gap-3xl">
        {/* Left — copy */}
        <div className="flex max-w-[560px] flex-col gap-md">
          {/* Vistral · Valoración inteligente — pill */}
          <span className="inline-flex w-fit items-center gap-xs rounded-pill border border-line-subtle bg-card/90 px-md py-xs text-text-sm font-medium text-ink shadow-card backdrop-blur-2">
            <img
              src="/assets/vistral-logo.svg"
              alt=""
              aria-hidden
              width={18}
              height={18}
              className="h-[18px] w-[18px]"
            />
            <span className="font-semibold">Vistral</span>
            <span aria-hidden className="text-ink-muted">·</span>
            <span className="text-ink-secondary">{t('hero.toolTag')}</span>
          </span>

          <h1 className="text-ink">
            {t('hero.title')}
            <span className="text-brand">{t('hero.titleHighlight')}</span>
            {t('hero.titleEnd')}
          </h1>

          <p className="text-text-lg text-ink-secondary">{t('hero.subtitle')}</p>

          {/* CTA row */}
          <div className="mt-sm flex flex-wrap items-center gap-md">
            <button
              type="button"
              onClick={onStart}
              className="btn-primary h-12 px-xl text-text-lg shadow-level-2"
              autoFocus
            >
              {t('landing.cta')}
              <ArrowRight className="h-5 w-5" />
            </button>
            <span className="text-text-sm text-ink-muted">
              {t('landing.ctaHint')}
            </span>
          </div>

          {/* Trust chips — inline */}
          <ul className="mt-sm flex flex-wrap gap-sm">
            {TRUST_CHIPS.map(({ icon: Icon, key }) => (
              <li
                key={key}
                className="inline-flex items-center gap-xs rounded-pill border border-line-subtle bg-card/60 px-md py-xs text-text-sm text-ink-secondary"
              >
                <Icon aria-hidden strokeWidth={1.5} className="h-4 w-4 shrink-0 text-ink-muted" />
                {t(key)}
              </li>
            ))}
          </ul>
        </div>

        {/* Right — photograph */}
        <figure className="relative mx-auto w-full max-w-[520px] lg:justify-self-end">
          <div
            aria-hidden
            className="absolute -inset-md -z-10 rounded-card bg-primary/5"
          />
          <div className="relative overflow-hidden rounded-card border border-line-subtle bg-surface-tint shadow-level-3">
            <img
              src="/assets/hero-section.png"
              alt={t('hero.imageAlt')}
              className="block aspect-[4/5] w-full object-cover"
              style={{ objectPosition: '50% 35%' }}
              loading="eager"
              fetchPriority="high"
            />
            <span
              aria-hidden
              className="pointer-events-none absolute inset-0 rounded-card ring-1 ring-inset ring-white/10"
            />
          </div>
        </figure>
      </div>
    </section>
  )
}
