import { useTranslation } from 'react-i18next'
import { Globe } from 'lucide-react'

const LANGS = [
  { code: 'es', label: 'ES' },
  { code: 'en', label: 'EN' },
] as const

export function LanguageSwitcher() {
  const { i18n } = useTranslation()

  return (
    <div className="flex items-center gap-xs">
      <Globe className="h-4 w-4 text-ink-muted" />
      {LANGS.map(({ code, label }, i) => (
        <span key={code} className="flex items-center">
          {i > 0 && <span className="mx-0-5 text-text-sm text-ink-muted">/</span>}
          <button
            type="button"
            onClick={() => i18n.changeLanguage(code)}
            className={[
              'rounded-sm px-xs py-0-5 text-text-sm font-semibold transition-colors',
              i18n.language === code
                ? 'bg-primary/10 text-brand'
                : 'text-ink-muted hover:text-ink',
            ].join(' ')}
          >
            {label}
          </button>
        </span>
      ))}
    </div>
  )
}
