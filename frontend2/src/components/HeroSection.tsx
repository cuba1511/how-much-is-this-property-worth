import { useTranslation } from 'react-i18next'

export function HeroSection() {
  const { t } = useTranslation()

  return (
    <section className="bg-surface pt-2xl pb-xl px-md md:px-xl">
      <h1>
        {t('hero.title')}<span className="text-primary">{t('hero.titleHighlight')}</span>{t('hero.titleEnd')}
      </h1>
      <p className="text-ink-secondary max-w-[560px] mt-3">
        {t('hero.subtitle')}
      </p>
    </section>
  )
}
