import { Check } from 'lucide-react'
import { cn } from './utils'

export interface LanguageOption {
  code: string
  nativeName: string
  secondaryName?: string
}

export interface LanguagePickerProps {
  label: string
  languages: LanguageOption[]
  value?: string
  onChange: (code: string) => void
  className?: string
}

export function LanguagePicker({ label, languages, value, onChange, className }: LanguagePickerProps) {
  return (
    <div role="radiogroup" aria-label={label} className={cn('grid grid-cols-2 gap-3', className)}>
      {languages.map((language) => {
        const selected = language.code === value
        return (
          <button key={language.code} type="button" role="radio" aria-checked={selected} onClick={() => onChange(language.code)} className={cn('relative min-h-[72px] rounded-card border p-3 text-left transition-colors duration-fast ease-out', selected ? 'border-cyan bg-cyan-50' : 'border-hairline bg-card')}>
            <span className="block text-base font-semibold text-navy">{language.nativeName}</span>
            {language.secondaryName && <span className="mt-0.5 block text-xs text-muted">{language.secondaryName}</span>}
            {selected && <Check aria-hidden="true" className="absolute right-3 top-3 h-5 w-5 text-cyan" />}
          </button>
        )
      })}
    </div>
  )
}
