import { z } from 'zod'

export const propertyTypes = ['casa', 'piso'] as const
export type PropertyType = (typeof propertyTypes)[number]

export const propertyConditions = ['obra_nueva', 'buen_estado', 'a_reformar'] as const
export type PropertyCondition = (typeof propertyConditions)[number]

export const featureKeys = ['pool', 'terrace', 'elevator', 'parking'] as const
export type FeatureKey = (typeof featureKeys)[number]

const featuresSchema = z.object({
  pool: z.boolean(),
  terrace: z.boolean(),
  elevator: z.boolean(),
  parking: z.boolean(),
})

export const step1Schema = z.object({
  propertyType: z.enum(propertyTypes),
  features: featuresSchema,
})

export const step2Schema = z.object({
  address: z.string().min(1),
})

export const step3Schema = z.object({
  propertyCondition: z.enum(propertyConditions),
  m2: z.number().int().min(20).max(500),
  bedrooms: z.number().int().min(0).max(10),
  bathrooms: z.number().int().min(1).max(5),
})

export const valuationRequestSchema = step1Schema.merge(step2Schema).merge(step3Schema)

export type ValuationRequestForm = z.infer<typeof valuationRequestSchema>
