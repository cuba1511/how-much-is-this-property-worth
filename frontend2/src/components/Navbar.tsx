import { LanguageSwitcher } from '@/components/LanguageSwitcher'

export function Navbar() {
  return (
    <header className="sticky top-0 z-50 bg-surface border-b border-line">
      <div className="max-w-7xl mx-auto px-md md:px-xl h-16 flex items-center justify-between">
        <a href="/" aria-label="PropHero">
          <img src="/logo.svg" alt="PropHero" width={125} height={28} />
        </a>
        <LanguageSwitcher />
      </div>
    </header>
  )
}
