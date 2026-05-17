import { useTranslation } from 'react-i18next'
import type { CadastralUnit } from '@/lib/types'

interface UnitSelectionStepProps {
  units: CadastralUnit[]
  selected: CadastralUnit | null
  onSelect: (unit: CadastralUnit) => void
  addressLabel: string
  disabled?: boolean
}

function display(value: string | null | undefined): string {
  if (value == null || value === '') return '—'
  return value
}

/** Catastro encodes floors as strings: -1 = sótano, 00 = bajo, 01 = primero… */
function formatFloor(floor: string | null | undefined): string {
  if (floor == null || floor === '') return '—'
  if (floor === '-1') return 'Sótano'
  if (floor === '00') return 'Bajo'
  if (/^\d+$/.test(floor)) return String(parseInt(floor, 10))
  return floor
}

export function UnitSelectionStep({
  units,
  selected,
  onSelect,
  addressLabel,
  disabled = false,
}: UnitSelectionStepProps) {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col gap-sm">
      <div>
        <h3 className="text-sm font-semibold text-ink">{t('catastro.selectTitle')}</h3>
        <p className="mt-0.5 text-xs text-ink-secondary">{t('catastro.selectHint')}</p>
      </div>

      <div className="rounded-lg border border-primary/15 bg-primary/5 px-sm py-2 text-xs text-ink leading-snug">
        {addressLabel}
      </div>

      <div className="overflow-hidden rounded-lg border border-line">
        <div
          className="grid grid-cols-[1fr_1fr_1fr_1fr_2rem] gap-x-2 border-b border-line bg-surface-tint px-sm py-1.5 text-[10px] font-semibold uppercase tracking-wide text-ink-muted"
          role="row"
        >
          <span>{t('catastro.block')}</span>
          <span>{t('catastro.staircase')}</span>
          <span>{t('catastro.floor')}</span>
          <span>{t('catastro.door')}</span>
          <span />
        </div>

        <ul
          className="max-h-[min(280px,42vh)] overflow-y-auto overscroll-contain"
          role="listbox"
          aria-label={t('catastro.selectTitle')}
        >
          {units.map((unit) => {
            const isSelected = selected?.cadastral_reference === unit.cadastral_reference
            return (
              <li key={unit.cadastral_reference} role="presentation">
                <button
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  disabled={disabled}
                  onClick={() => onSelect(unit)}
                  className={`grid w-full grid-cols-[1fr_1fr_1fr_1fr_2rem] items-center gap-x-2 border-b border-line px-sm py-2 text-left text-xs transition-colors last:border-0 disabled:cursor-not-allowed disabled:opacity-60 ${
                    isSelected ? 'bg-primary/8' : 'hover:bg-surface-tint'
                  }`}
                >
                  <span className="text-ink-secondary">{display(unit.block)}</span>
                  <span className="text-ink-secondary">{display(unit.staircase)}</span>
                  <span className="font-medium text-ink">{formatFloor(unit.floor)}</span>
                  <span className="font-medium text-ink">{display(unit.door)}</span>
                  <span className="flex justify-center">
                    <span
                      className={`flex h-4 w-4 items-center justify-center rounded-full border-2 ${
                        isSelected ? 'border-primary bg-primary' : 'border-ink-muted bg-surface'
                      }`}
                      aria-hidden
                    >
                      {isSelected && (
                        <span className="h-1.5 w-1.5 rounded-full bg-white" />
                      )}
                    </span>
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}
