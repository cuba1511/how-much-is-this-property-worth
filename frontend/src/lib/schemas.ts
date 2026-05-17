import { z } from 'zod'

export const propertyTypes = ['casa', 'piso'] as const
export type PropertyType = (typeof propertyTypes)[number]

export const propertyConditions = ['obra_nueva', 'buen_estado', 'a_reformar'] as const
export type PropertyCondition = (typeof propertyConditions)[number]

export const featureKeys = ['pool', 'terrace', 'elevator', 'parking'] as const
export type FeatureKey = (typeof featureKeys)[number]

export const valuationIntents = ['sell', 'buy', 'rent_out', 'rent', 'info'] as const
export type ValuationIntent = (typeof valuationIntents)[number]

export const sellReasons = [
  'upgrade',
  'downsize',
  'investment',
  'inheritance',
  'relocation',
  'other',
] as const
export type SellReason = (typeof sellReasons)[number]

export const sellTimelines = ['asap', '3_months', '6_months', '12_months', 'flexible'] as const
export type SellTimeline = (typeof sellTimelines)[number]

const featuresSchema = z.object({
  pool: z.boolean(),
  terrace: z.boolean(),
  elevator: z.boolean(),
  parking: z.boolean(),
})

/** Paso 1 — El inmueble (dirección) */
export const step1Schema = z.object({
  address: z.string().min(1),
})

/** Paso 2 — Tipo de inmueble y extras */
export const step2Schema = z.object({
  propertyType: z.enum(propertyTypes),
  features: featuresSchema,
})

/** Paso 3 — Estado, superficie, habitaciones y baños */
export const step3Schema = z.object({
  propertyCondition: z.enum(propertyConditions),
  m2: z.number().int().min(20).max(500),
  bedrooms: z.number().int().min(0).max(10),
  bathrooms: z.number().int().min(1).max(5),
})

/** Paso 4 — Para qué necesitas la valoración */
export const step4Schema = z
  .object({
    valuationIntent: z.enum(valuationIntents),
    sellReason: z.enum(sellReasons).optional(),
    sellTimeline: z.enum(sellTimelines).optional(),
  })
  .superRefine((data, ctx) => {
    if (data.valuationIntent !== 'sell') return
    if (!data.sellReason) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['sellReason'],
        message: 'Required',
      })
    }
    if (!data.sellTimeline) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['sellTimeline'],
        message: 'Required',
      })
    }
  })

export const valuationRequestSchema = step1Schema
  .merge(step2Schema)
  .merge(step3Schema)
  .merge(step4Schema)

export type ValuationRequestForm = z.infer<typeof valuationRequestSchema>
