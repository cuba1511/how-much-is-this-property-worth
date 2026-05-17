import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { User, Mail } from 'lucide-react'
import { isValidPhoneNumber, type Value } from 'react-phone-number-input'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { PhoneInputField } from '@/components/ui/phone-input'
import { LeadAnalyzingProgress } from '@/components/LeadAnalyzingProgress'
import type { LeadData } from '@/components/LeadDialog'

interface LeadStepProps {
  onSubmit: (lead: LeadData) => void
  submitting: boolean
}

export function LeadStep({ onSubmit, submitting }: LeadStepProps) {
  const { t } = useTranslation()
  const [lead, setLead] = useState<LeadData>({ fullName: '', email: '', phone: '' })
  const [errors, setErrors] = useState<Partial<Record<keyof LeadData, string>>>({})

  function validate(): boolean {
    const next: typeof errors = {}
    if (!lead.fullName.trim()) next.fullName = t('lead.nameError')
    if (!lead.email.trim()) {
      next.email = t('lead.emailError')
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(lead.email)) {
      next.email = t('lead.emailInvalid')
    }
    if (!lead.phone.trim()) {
      next.phone = t('lead.phoneError')
    } else if (!isValidPhoneNumber(lead.phone)) {
      next.phone = t('lead.phoneInvalid')
    }
    setErrors(next)
    return Object.keys(next).length === 0
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (validate()) onSubmit(lead)
  }

  function update(field: keyof LeadData, value: string) {
    setLead((prev) => ({ ...prev, [field]: value }))
    if (errors[field]) setErrors((prev) => ({ ...prev, [field]: undefined }))
  }

  if (submitting) {
    return (
      <div className="flex flex-col gap-md py-sm">
        <div>
          <h2 className="text-base font-semibold text-ink">{t('lead.analyzing.title')}</h2>
          <p className="mt-0.5 text-sm text-ink-secondary">{t('lead.analyzing.description')}</p>
        </div>
        <LeadAnalyzingProgress active={submitting} />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-md">
      <div>
        <h2 className="text-base font-semibold text-ink">{t('lead.title')}</h2>
        <p className="mt-0.5 text-sm text-ink-secondary">{t('lead.description')}</p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-md" noValidate>
        <div className="flex flex-col gap-xs">
          <Label htmlFor="lead-name">{t('lead.name')}</Label>
          <div className="relative">
            <User className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" />
            <Input
              id="lead-name"
              placeholder={t('lead.namePlaceholder')}
              value={lead.fullName}
              onChange={(e) => update('fullName', e.target.value)}
              className="pl-9"
            />
          </div>
          {errors.fullName && <p className="text-xs text-destructive">{errors.fullName}</p>}
        </div>

        <div className="flex flex-col gap-xs">
          <Label htmlFor="lead-email">{t('lead.email')}</Label>
          <div className="relative">
            <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" />
            <Input
              id="lead-email"
              type="email"
              placeholder={t('lead.emailPlaceholder')}
              value={lead.email}
              onChange={(e) => update('email', e.target.value)}
              className="pl-9"
            />
          </div>
          {errors.email && <p className="text-xs text-destructive">{errors.email}</p>}
        </div>

        <div className="flex flex-col gap-xs">
          <Label htmlFor="lead-phone">{t('lead.phone')}</Label>
          <PhoneInputField
            id="lead-phone"
            defaultCountry="ES"
            value={lead.phone as Value}
            onChange={(val) => update('phone', val ?? '')}
            placeholder={t('lead.phonePlaceholder')}
            error={!!errors.phone}
          />
          {errors.phone && <p className="text-xs text-destructive">{errors.phone}</p>}
        </div>

        <button type="submit" className="btn-primary mt-xs w-full">
          {t('lead.submit')}
        </button>

        <p className="text-center text-xs text-ink-muted">{t('lead.privacy')}</p>
      </form>
    </div>
  )
}
