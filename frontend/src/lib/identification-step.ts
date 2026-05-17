import type { CatastroLookupStatus } from '@/components/steps/PropertyIdentificationStep'
import type { CadastralUnit, ResolvedAddress } from '@/lib/types'

/** True when step 1 (El inmueble) allows advancing — blocks Next while Catastro is loading. */
export function canProceedFromIdentification(
  address: ResolvedAddress | null,
  lookupStatus: CatastroLookupStatus,
  unitsCount: number,
  selectedUnit: CadastralUnit | null,
): boolean {
  if (!address?.house_number) return false
  if (lookupStatus === 'loading' || lookupStatus === 'idle') return false
  if (lookupStatus === 'done' && unitsCount > 1 && !selectedUnit) return false
  return true
}
