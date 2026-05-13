import PhoneInput, {
  type Country,
  type Value,
} from 'react-phone-number-input'
import flags from 'react-phone-number-input/flags'
import 'react-phone-number-input/style.css'
import { cn } from '@/lib/utils'

interface PhoneInputFieldProps {
  value: Value | undefined
  onChange: (value: Value | undefined) => void
  defaultCountry?: Country
  id?: string
  placeholder?: string
  disabled?: boolean
  className?: string
  error?: boolean
}

export function PhoneInputField({
  value,
  onChange,
  defaultCountry = 'ES',
  id,
  placeholder,
  disabled,
  className,
  error,
}: PhoneInputFieldProps) {
  return (
    <div
      className={cn(
        'flex h-10 w-full rounded-input border border-line bg-page text-text-md transition-colors duration-fast',
        'focus-within:border-line-brand focus-within:ring-2 focus-within:ring-primary/20',
        'placeholder:text-ink-muted',
        'disabled:cursor-not-allowed disabled:opacity-50',
        error && 'border-line-error focus-within:border-line-error focus-within:ring-destructive/20',
        '[&_.PhoneInput]:flex [&_.PhoneInput]:w-full [&_.PhoneInput]:items-center',
        // Country select button
        '[&_.PhoneInputCountry]:flex [&_.PhoneInputCountry]:items-center [&_.PhoneInputCountry]:gap-1 [&_.PhoneInputCountry]:pl-3 [&_.PhoneInputCountry]:pr-2',
        '[&_.PhoneInputCountrySelect]:absolute [&_.PhoneInputCountrySelect]:inset-0 [&_.PhoneInputCountrySelect]:opacity-0 [&_.PhoneInputCountrySelect]:cursor-pointer',
        '[&_.PhoneInputCountryIcon]:w-5 [&_.PhoneInputCountryIcon]:h-auto [&_.PhoneInputCountryIcon]:rounded-[2px] [&_.PhoneInputCountryIcon]:overflow-hidden',
        '[&_.PhoneInputCountryIcon--border]:shadow-none [&_.PhoneInputCountryIcon--border]:bg-transparent',
        '[&_.PhoneInputCountryIcon>svg]:w-5 [&_.PhoneInputCountryIcon>svg]:h-auto',
        '[&_.PhoneInputCountrySelectArrow]:ml-0 [&_.PhoneInputCountrySelectArrow]:w-2 [&_.PhoneInputCountrySelectArrow]:h-2 [&_.PhoneInputCountrySelectArrow]:border-current [&_.PhoneInputCountrySelectArrow]:opacity-50',
        // Number input
        '[&_.PhoneInputInput]:flex-1 [&_.PhoneInputInput]:bg-transparent [&_.PhoneInputInput]:outline-none [&_.PhoneInputInput]:border-none [&_.PhoneInputInput]:py-1 [&_.PhoneInputInput]:pr-3 [&_.PhoneInputInput]:text-text-md [&_.PhoneInputInput]:text-ink [&_.PhoneInputInput]:placeholder-ink-muted',
        // Divider between flag selector and number
        '[&_.PhoneInputCountry]:border-r [&_.PhoneInputCountry]:border-line-subtle',
        className,
      )}
    >
      <PhoneInput
        flags={flags}
        international
        defaultCountry={defaultCountry}
        value={value}
        onChange={onChange}
        id={id}
        placeholder={placeholder}
        disabled={disabled}
        countryCallingCodeEditable={false}
      />
    </div>
  )
}
