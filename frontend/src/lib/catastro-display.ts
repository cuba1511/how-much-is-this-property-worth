/** Human-readable Catastro floor codes for UI. */
export function formatCatastroFloor(floor: string | null | undefined): string {
  if (floor == null || floor === '') return ''
  if (floor === '-1') return 'Sótano'
  if (floor === '00') return 'Bajo'
  if (/^\d+$/.test(floor)) return String(parseInt(floor, 10))
  return floor
}

export function formatUnitSummary(
  unit: { floor?: string | null; door?: string | null; label: string },
): string {
  const parts: string[] = []
  const floor = formatCatastroFloor(unit.floor)
  if (floor) parts.push(`Planta ${floor}`)
  if (unit.door) parts.push(`Puerta ${unit.door}`)
  return parts.length > 0 ? parts.join(' · ') : unit.label
}
