const esNumberFormat = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0 })
const esCurrencyFormat = new Intl.NumberFormat('es-ES', {
  style: 'currency',
  currency: 'EUR',
  maximumFractionDigits: 0,
})

export function formatPrice(value: number | null | undefined): string {
  if (value == null) return '—'
  return esCurrencyFormat.format(value)
}

export function formatPricePerM2(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${esNumberFormat.format(value)} €/m²`
}

export function formatPct(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${value.toFixed(1)}%`
}

export function formatDays(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${Math.round(value)}d`
}

export function formatNumber(value: number | null | undefined): string {
  if (value == null) return '—'
  return esNumberFormat.format(value)
}
