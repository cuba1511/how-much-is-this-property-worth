import { LanguageSwitcher } from '@/components/LanguageSwitcher'

export function Navbar() {
  return (
    <header
      role="banner"
      className="sticky top-0 z-50 border-b border-line bg-surface/90 backdrop-blur supports-[backdrop-filter]:bg-surface/75"
    >
      <div className="mx-auto flex h-16 w-full max-w-7xl items-center justify-between px-md md:px-xl">
        <a
          href="/"
          aria-label="PropHero"
          className="inline-flex items-center rounded-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-primary"
        >
          <img src="/logo.svg" alt="PropHero" width={125} height={28} className="h-7 w-auto" />
        </a>
        <LanguageSwitcher />
      </div>
    </header>
  )
}
