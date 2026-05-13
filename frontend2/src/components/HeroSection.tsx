import { useTranslation } from 'react-i18next'
import { ArrowRight, BarChart3, Clock, MapPin } from 'lucide-react'

interface HeroSectionProps {
  onStart: () => void
}

export function HeroSection({ onStart }: HeroSectionProps) {
  const { t } = useTranslation()

  return (
    <section className="flex min-h-[calc(100svh-4rem)] items-center px-md md:px-xl py-xl">
      <div className="mx-auto grid w-full max-w-6xl items-center gap-xl md:gap-2xl md:grid-cols-[1.05fr_1fr]">
        {/* Left: copy + CTA */}
        <div className="flex flex-col items-start gap-md">
          <span className="inline-flex items-center gap-2 rounded-pill border border-line bg-surface-tint px-3 py-1 text-xs font-medium text-ink-secondary">
            <img
              src="/vistral-logo.svg"
              alt=""
              aria-hidden="true"
              width={14}
              height={14}
              className="h-3.5 w-3.5"
            />
            <span className="font-semibold text-ink">Vistral</span>
            <span className="text-ink-muted">·</span>
            <span>{t('hero.badge')}</span>
          </span>

          <h1 className="!my-0 text-balance text-[2rem] md:text-[2.5rem] font-semibold leading-[1.1] tracking-tight">
            {t('hero.title')}
            <span className="text-primary whitespace-nowrap">{t('hero.titleHighlight')}</span>
            {t('hero.titleEnd')}
          </h1>

          <p className="text-base leading-relaxed text-ink-secondary text-balance max-w-[460px]">
            {t('hero.subtitle')}
          </p>

          <div className="mt-xs flex flex-wrap items-center gap-sm">
            <button
              type="button"
              onClick={onStart}
              className="btn-primary whitespace-nowrap px-6 py-3 text-sm"
            >
              {t('form.submit')}
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </button>
            <span className="text-xs text-ink-muted">{t('hero.ctaCaption')}</span>
          </div>

          <ul className="mt-sm flex flex-col gap-xs">
            {[
              { icon: Clock, key: 'impacts.resultTime' },
              { icon: MapPin, key: 'impacts.realTimePrices' },
              { icon: BarChart3, key: 'impacts.propertiesSold' },
            ].map(({ icon: Icon, key }) => (
              <li
                key={key}
                className="inline-flex w-fit items-center gap-2 rounded-pill border border-line bg-surface px-3 py-1 text-xs text-ink-secondary"
              >
                <Icon className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden="true" />
                <span>{t(key)}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Right: photo */}
        <div className="relative w-full">
          <div className="relative mx-auto aspect-[4/5] w-full max-w-[460px] overflow-hidden rounded-3xl border border-line bg-surface-muted shadow-lift">
            <img
              src="/piso.png"
              alt={t('hero.imageAlt')}
              className="h-full w-full object-cover"
              loading="eager"
              decoding="async"
            />
          </div>
        </div>
      </div>
    </section>
  )
}
