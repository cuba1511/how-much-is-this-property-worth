import type { Listing } from '@/lib/types'

export type ConfidenceLevel = 'high' | 'medium' | 'low'

export function getConfidenceLevel(finalStage: string, totalComparables: number): ConfidenceLevel {
  if ((finalStage === 'same_street' || finalStage === 'same_microzone') && totalComparables >= 10)
    return 'high'
  if (finalStage === 'same_local_area' && totalComparables >= 5)
    return 'medium'
  return 'low'
}

export function estimateSalePrice(estimatedValue: number, gapPct: number): number {
  return Math.round(estimatedValue * (1 - gapPct / 100))
}

export function bedroomMatchedAvg(listings: Listing[], bedrooms: number): number | null {
  const matched = listings.filter(
    (l) => l.bedrooms === bedrooms && l.price_per_m2 != null,
  )
  if (matched.length < 3) return null
  const sum = matched.reduce((acc, l) => acc + l.price_per_m2!, 0)
  return Math.round(sum / matched.length)
}

export interface PriceDistributionBin {
  label: string
  count: number
  rangeMin: number
  rangeMax: number
}

export function priceDistribution(listings: Listing[], bins = 5): PriceDistributionBin[] {
  const prices = listings
    .map((l) => l.price)
    .filter((p): p is number => p != null)
    .sort((a, b) => a - b)

  if (prices.length < 2) return []

  const min = prices[0]
  const max = prices[prices.length - 1]
  const step = (max - min) / bins

  return Array.from({ length: bins }, (_, i) => {
    const rangeMin = Math.round(min + step * i)
    const rangeMax = i === bins - 1 ? max : Math.round(min + step * (i + 1))
    const count = prices.filter(
      (p) => p >= rangeMin && (i === bins - 1 ? p <= rangeMax : p < rangeMax),
    ).length
    const fmt = (v: number) =>
      v >= 1000 ? `${Math.round(v / 1000)}k` : String(v)
    return { label: `${fmt(rangeMin)}-${fmt(rangeMax)}`, count, rangeMin, rangeMax }
  })
}

export function stageRadiusMeters(stage: string): number {
  switch (stage) {
    case 'same_street': return 150
    case 'same_microzone': return 500
    case 'same_local_area': return 1500
    default: return 3000
  }
}

export interface DaysOnMarketBucket {
  label: string
  count: number
}

export function daysOnMarketBuckets(daysArr: number[]): DaysOnMarketBucket[] {
  return [
    { label: '<30d', count: daysArr.filter((d) => d < 30).length },
    { label: '30-60d', count: daysArr.filter((d) => d >= 30 && d < 60).length },
    { label: '60-90d', count: daysArr.filter((d) => d >= 60 && d < 90).length },
    { label: '>90d', count: daysArr.filter((d) => d >= 90).length },
  ]
}
