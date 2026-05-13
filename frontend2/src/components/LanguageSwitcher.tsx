import { useTranslation } from 'react-i18next'
import { Globe } from 'lucide-react'

const LANGS = [
  { code: 'es', label: 'ES' },
  { code: 'en', label: 'EN' },
] as const

export function LanguageSwitcher() {
  const { i18n } = useTranslation()

  return (
    <div className="flex items-center gap-1">
      <Globe className="h-4 w-4 text-ink-muted" />
      {LANGS.map(({ code, label }, i) => (
        <span key={code} className="flex items-center">
          {i > 0 && <span className="text-ink-muted text-xs mx-0.5">/</span>}
          <button
            type="button"
            onClick={() => i18n.changeLanguage(code)}
            className={`text-xs font-semibold px-1 py-0.5 rounded transition-colors ${
              i18n.language === code
                ? 'text-primary bg-primary/10'
                : 'text-ink-muted hover:text-ink'
            }`}
          >
            {label}
          </button>
        </span>
      ))}
    </div>
  )
}
