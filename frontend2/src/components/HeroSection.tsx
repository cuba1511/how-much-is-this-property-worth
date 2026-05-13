import { useTranslation } from 'react-i18next'

export function HeroSection() {
  const { t } = useTranslation()

  return (
    <section className="px-md md:px-xl pt-2xl pb-xl">
      <div className="mx-auto flex w-full max-w-2xl flex-col items-center gap-sm text-center">
        <h1 className="text-balance">
          {t('hero.title')}
          <span className="text-primary">{t('hero.titleHighlight')}</span>
          {t('hero.titleEnd')}
        </h1>
        <p className="typo-text-lg text-ink-secondary text-balance max-w-[560px]">
          {t('hero.subtitle')}
        </p>
      </div>
    </section>
  )
}
