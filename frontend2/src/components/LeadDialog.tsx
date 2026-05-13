import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { User, Mail, Loader2 } from 'lucide-react'
import { isValidPhoneNumber, type Value } from 'react-phone-number-input'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { PhoneInputField } from '@/components/ui/phone-input'

export interface LeadData {
  fullName: string
  email: string
  phone: string
}

interface LeadDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (lead: LeadData) => void
  submitting: boolean
}

export function LeadDialog({ open, onOpenChange, onSubmit, submitting }: LeadDialogProps) {
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

  return (
    <Dialog open={open} onOpenChange={submitting ? undefined : onOpenChange}>
      <DialogContent
        className="sm:max-w-md"
        onInteractOutside={(e) => { if (submitting) e.preventDefault() }}
        onEscapeKeyDown={(e) => { if (submitting) e.preventDefault() }}
      >
        <DialogHeader>
          <DialogTitle>{t('lead.title')}</DialogTitle>
          <DialogDescription>
            {t('lead.description')}
          </DialogDescription>
        </DialogHeader>

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
                autoFocus
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

          <button
            type="submit"
            disabled={submitting}
            className="btn-primary mt-sm w-full disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                {t('form.analyzing')}
              </>
            ) : (
              t('lead.submit')
            )}
          </button>

          <p className="text-center text-xs text-ink-muted">
            {t('lead.privacy')}
          </p>
        </form>
      </DialogContent>
    </Dialog>
  )
}
