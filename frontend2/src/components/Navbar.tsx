import { useTranslation } from 'react-i18next'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'

interface NavbarProps {
  onHome?: () => void
}

export function Navbar({ onHome }: NavbarProps) {
  const { t } = useTranslation()
  const clickable = typeof onHome === 'function'

  const inner = (
    <>
      <img src="/logo.svg" alt="PropHero" width={125} height={28} className="h-7 w-auto" />
      <span
        aria-hidden
        className="hidden h-7 w-px bg-line sm:block"
      />
      <span className="hidden items-center gap-sm sm:inline-flex">
        <img
          src="/assets/vistral-logo.svg"
          alt=""
          aria-hidden
          width={28}
          height={28}
          className="h-7 w-7"
        />
        <span className="text-header-md font-semibold leading-none tracking-tight text-ink">
          Vistral
        </span>
      </span>
    </>
  )

  return (
    <header className="sticky top-0 z-50 border-b border-line-subtle bg-card/80 backdrop-blur-3">
      <div className="container mx-auto flex h-16 items-center justify-between">
        {clickable ? (
          <button
            type="button"
            onClick={onHome}
            aria-label={t('nav.backHome')}
            className="inline-flex items-center gap-sm rounded-pill px-xs py-xs transition-colors hover:bg-surface-muted"
          >
            {inner}
          </button>
        ) : (
          <a
            href="/"
            aria-label="PropHero · Vistral"
            className="inline-flex items-center gap-sm"
          >
            {inner}
          </a>
        )}
        <LanguageSwitcher />
      </div>
    </header>
  )
}
