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
    accent: 'border-line-success/40',
    badge:  'alert-success',
    icon:   MapPin,
  },
  same_microzone: {
    accent: 'border-line-brand/30',
    badge:  'alert-info',
    icon:   Grid3X3,
  },
  same_local_area: {
    accent: 'border-line-warning/40',
    badge:  'alert-warning',
    icon:   MapPinned,
  },
  municipality: {
    accent: 'border-line-subtle',
    badge:  'bg-surface-muted text-ink-secondary',
    icon:   MapPinned,
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
      <div className="mb-md flex flex-wrap items-center justify-between gap-sm">
        <h2 className="text-header-sm">
          {t('results.comparablesSection.title', { count: listings.length })}
        </h2>
        <div className="flex gap-xs">
          {(['price', 'ppm', 'sizeMatch'] as const).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setSortBy(key)}
              className={[
                'rounded-pill px-md py-xs text-text-sm font-medium transition-colors',
                sortBy === key
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-surface-muted text-ink-secondary hover:bg-surface-tint',
              ].join(' ')}
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
              <div className="mb-sm flex items-center gap-sm">
                <span className={`inline-flex items-center gap-xs rounded-pill px-md py-xs text-text-sm font-semibold ${style.badge}`}>
                  <Icon className="h-3 w-3" />
                  {t(`results.stages.${group.key}`, group.key)}
                </span>
                <span className="text-text-sm text-ink-muted">
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
                    className={`group flex flex-col overflow-hidden rounded-lg border-2 bg-card shadow-level-1 transition-shadow hover:shadow-level-3 ${style.accent}`}
                  >
                    {listing.image_url && (
                      <div className="h-36 overflow-hidden bg-surface-muted">
                        <img
                          src={listing.image_url}
                          alt={listing.title}
                          className="h-full w-full object-cover transition-transform duration-normal group-hover:scale-105"
                          loading="lazy"
                        />
                      </div>
                    )}
                    <div className="flex flex-1 flex-col gap-xs p-md">
                      <p className="line-clamp-2 text-text-md font-semibold leading-snug text-ink">
                        {listing.title}
                      </p>
                      {listing.address && (
                        <p className="line-clamp-1 text-text-sm text-ink-muted">{listing.address}</p>
                      )}

                      <div className="mt-xs flex flex-wrap gap-xs">
                        {listing.price_per_m2 != null && (
                          <span className="inline-flex items-center rounded-pill bg-primary/10 px-sm py-0-5 text-text-xs font-medium text-brand">
                            {formatPricePerM2(listing.price_per_m2)}
                          </span>
                        )}
                        {listing.floor && (
                          <span className="inline-flex items-center rounded-pill bg-surface-muted px-sm py-0-5 text-text-xs font-medium text-ink-secondary">
                            {t('results.comparablesSection.floor', { floor: listing.floor })}
                          </span>
                        )}
                      </div>

                      <div className="mt-auto flex items-center justify-between gap-sm pt-sm">
                        <div>
                          {listing.price != null && (
                            <p className="text-text-lg font-semibold text-ink">{formatPrice(listing.price)}</p>
                          )}
                          <div className="flex flex-wrap gap-sm">
                            {listing.m2 != null && (
                              <span className="text-text-sm text-ink-secondary">{t('results.m2', { count: listing.m2 })}</span>
                            )}
                            {listing.bedrooms != null && (
                              <span className="text-text-sm text-ink-secondary">{t('results.rooms', { count: listing.bedrooms })}</span>
                            )}
                            {listing.bathrooms != null && (
                              <span className="text-text-sm text-ink-secondary">{t('results.baths', { count: listing.bathrooms })}</span>
                            )}
                          </div>
                        </div>
                        <ExternalLink className="h-3.5 w-3.5 shrink-0 text-ink-muted transition-colors group-hover:text-brand" />
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
