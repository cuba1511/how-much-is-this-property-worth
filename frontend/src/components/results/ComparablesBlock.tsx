import { useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { ExternalLink, MapPin, Grid3X3, MapPinned } from 'lucide-react'
import type { Listing } from '@/lib/types'
import { formatPrice, formatPricePerM2 } from './shared/formatters'

type SortKey = 'price' | 'ppm' | 'sizeMatch'

interface ComparablesBlockProps {
  listings: Listing[]
  requestM2: number
}

interface StageGroup {
  key: string
  listings: Listing[]
}

const STAGE_ORDER = ['same_street', 'same_microzone', 'same_local_area', 'municipality']

const STAGE_STYLES: Record<string, { accent: string; badge: string; icon: typeof MapPin }> = {
  same_street: {
    accent: 'border-emerald-200 dark:border-emerald-800/60',
    badge: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400',
    icon: MapPin,
  },
  same_microzone: {
    accent: 'border-sky-200 dark:border-sky-800/60',
    badge: 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-400',
    icon: Grid3X3,
  },
  same_local_area: {
    accent: 'border-amber-200 dark:border-amber-800/60',
    badge: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400',
    icon: MapPinned,
  },
  municipality: {
    accent: 'border-slate-200 dark:border-slate-700',
    badge: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
    icon: MapPinned,
  },
}

const DEFAULT_STYLE = STAGE_STYLES.municipality

function sortListings(listings: Listing[], sortBy: SortKey, requestM2: number): Listing[] {
  const copy = [...listings]
  switch (sortBy) {
    case 'price':
      return copy.sort((a, b) => (a.price ?? 0) - (b.price ?? 0))
    case 'ppm':
      return copy.sort((a, b) => (a.price_per_m2 ?? 0) - (b.price_per_m2 ?? 0))
    case 'sizeMatch':
      return copy.sort(
        (a, b) => Math.abs((a.m2 ?? 0) - requestM2) - Math.abs((b.m2 ?? 0) - requestM2),
      )
  }
}

export function ComparablesBlock({ listings, requestM2 }: ComparablesBlockProps) {
  const { t } = useTranslation()
  const [sortBy, setSortBy] = useState<SortKey>('price')

  const groups = useMemo<StageGroup[]>(() => {
    const map = new Map<string, Listing[]>()
    for (const l of listings) {
      const key = l.source_stage ?? 'other'
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(l)
    }
    return STAGE_ORDER
      .filter((s) => map.has(s))
      .map((s) => ({ key: s, listings: map.get(s)! }))
      .concat(
        [...map.entries()]
          .filter(([k]) => !STAGE_ORDER.includes(k))
          .map(([k, v]) => ({ key: k, listings: v })),
      )
  }, [listings])

  if (listings.length === 0) return null

  return (
    <div>
      <div className="flex items-center justify-between mb-md flex-wrap gap-sm">
        <h2 className="text-base font-semibold text-ink">
          {t('results.comparablesSection.title', { count: listings.length })}
        </h2>
        <div className="flex gap-1">
          {(['price', 'ppm', 'sizeMatch'] as const).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setSortBy(key)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                sortBy === key
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-surface-muted text-ink-secondary hover:bg-surface-tint'
              }`}
            >
              {t(`results.comparablesSection.sort.${key}`)}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-lg">
        {groups.map((group) => {
          const style = STAGE_STYLES[group.key] ?? DEFAULT_STYLE
          const Icon = style.icon
          const sorted = sortListings(group.listings, sortBy, requestM2)

          return (
            <section key={group.key}>
              <div className="flex items-center gap-2 mb-sm">
                <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${style.badge}`}>
                  <Icon className="h-3 w-3" />
                  {t(`results.stages.${group.key}`, group.key)}
                </span>
                <span className="text-xs text-ink-muted">
                  {t('results.comparablesSection.groupCount', { count: group.listings.length })}
                </span>
              </div>

              <div className="grid grid-cols-1 gap-md sm:grid-cols-2 lg:grid-cols-3">
                {sorted.map((listing, i) => (
                  <a
                    key={i}
                    href={listing.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`group flex flex-col rounded-xl border-2 bg-surface shadow-card transition hover:shadow-lift overflow-hidden ${style.accent}`}
                  >
                    {listing.image_url && (
                      <div className="h-36 overflow-hidden bg-surface-muted">
                        <img
                          src={listing.image_url}
                          alt={listing.title}
                          className="h-full w-full object-cover transition group-hover:scale-105"
                          loading="lazy"
                        />
                      </div>
                    )}
                    <div className="flex flex-col gap-xs p-md flex-1">
                      <p className="text-sm font-semibold text-ink line-clamp-2 leading-snug">
                        {listing.title}
                      </p>
                      {listing.address && (
                        <p className="text-xs text-ink-muted line-clamp-1">{listing.address}</p>
                      )}

                      <div className="flex flex-wrap gap-1 mt-1">
                        {listing.price_per_m2 != null && (
                          <span className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
                            {formatPricePerM2(listing.price_per_m2)}
                          </span>
                        )}
                        {listing.floor && (
                          <span className="inline-flex items-center rounded-full bg-surface-muted px-2 py-0.5 text-[10px] font-medium text-ink-secondary">
                            {t('results.comparablesSection.floor', { floor: listing.floor })}
                          </span>
                        )}
                      </div>

                      <div className="mt-auto pt-sm flex items-center justify-between gap-sm">
                        <div>
                          {listing.price != null && (
                            <p className="text-base font-bold text-ink">{formatPrice(listing.price)}</p>
                          )}
                          <div className="flex gap-sm flex-wrap">
                            {listing.m2 != null && (
                              <span className="text-xs text-ink-secondary">{t('results.m2', { count: listing.m2 })}</span>
                            )}
                            {listing.bedrooms != null && (
                              <span className="text-xs text-ink-secondary">{t('results.rooms', { count: listing.bedrooms })}</span>
                            )}
                            {listing.bathrooms != null && (
                              <span className="text-xs text-ink-secondary">{t('results.baths', { count: listing.bathrooms })}</span>
                            )}
                          </div>
                        </div>
                        <ExternalLink className="h-3.5 w-3.5 shrink-0 text-ink-muted group-hover:text-primary transition-colors" />
                      </div>
                    </div>
                  </a>
                ))}
              </div>
            </section>
          )
        })}
      </div>
    </div>
  )
}
