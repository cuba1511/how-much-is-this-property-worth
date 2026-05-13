import { z } from 'zod'

export const valuationRequestSchema = z.object({
  address: z.string().min(1),
  m2: z.number().int().min(20).max(500),
  bedrooms: z.number().int().min(1).max(10),
  bathrooms: z.number().int().min(1).max(5),
})

export type ValuationRequestForm = z.infer<typeof valuationRequestSchema>
