import { LanguageSwitcher } from '@/components/LanguageSwitcher'

export function Navbar() {
  return (
    <header
      role="banner"
      className="sticky top-0 z-50 border-b border-line bg-surface/90 backdrop-blur supports-[backdrop-filter]:bg-surface/75"
    >
      <div className="mx-auto flex h-16 w-full max-w-7xl items-center justify-between px-md md:px-xl">
        <div className="flex items-center gap-sm">
          <a
            href="/"
            aria-label="PropHero"
            className="inline-flex items-center rounded-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-primary"
          >
            <img src="/logo.svg" alt="PropHero" width={125} height={28} className="h-7 w-auto" />
          </a>
          <span aria-hidden="true" className="h-5 w-px bg-line" />
          <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-ink">
            <img
              src="/vistral-logo.svg"
              alt=""
              aria-hidden="true"
              width={18}
              height={18}
              className="h-[18px] w-[18px]"
            />
            Vistral
          </span>
        </div>
        <LanguageSwitcher />
      </div>
    </header>
  )
}
