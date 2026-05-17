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
        <h3 className="text-base font-semibold text-ink">{t('catastro.selectTitle')}</h3>
        <p className="mt-xs text-sm text-ink-secondary">{t('catastro.selectHint')}</p>
      </div>

      <div className="rounded-xl border border-primary/20 bg-primary/5 px-md py-sm text-sm text-ink">
        {addressLabel}
      </div>

      <div className="overflow-hidden rounded-xl border border-line">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line bg-surface-tint text-left text-xs font-medium text-ink-secondary">
              <th className="px-md py-sm">{t('catastro.block')}</th>
              <th className="px-md py-sm">{t('catastro.staircase')}</th>
              <th className="px-md py-sm">{t('catastro.floor')}</th>
              <th className="px-md py-sm">{t('catastro.door')}</th>
              <th className="w-10 px-sm py-sm" />
            </tr>
          </thead>
          <tbody>
            {units.map((unit) => {
              const isSelected = selected?.cadastral_reference === unit.cadastral_reference
              return (
                <tr
                  key={unit.cadastral_reference}
                  className={`border-b border-line last:border-0 transition-colors ${
                    isSelected ? 'bg-primary/5' : 'hover:bg-surface-tint'
                  }`}
                >
                  <td className="px-md py-sm">{display(unit.block)}</td>
                  <td className="px-md py-sm">{display(unit.staircase)}</td>
                  <td className="px-md py-sm">{display(unit.floor)}</td>
                  <td className="px-md py-sm">{display(unit.door)}</td>
                  <td className="px-sm py-sm text-center">
                    <input
                      type="radio"
                      name="cadastral-unit"
                      checked={isSelected}
                      disabled={disabled}
                      onChange={() => onSelect(unit)}
                      className="h-4 w-4 accent-primary"
                      aria-label={unit.label}
                    />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
