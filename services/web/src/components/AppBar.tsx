import { ArrowLeft, CircleHelp } from 'lucide-react'
import type { ReactNode } from 'react'
import { Logo } from './Logo'
import { cn } from './utils'

export interface AppBarProps {
  title: string
  backLabel?: string
  onBack?: () => void
  language?: string
  languageLabel?: string
  onLanguageClick?: () => void
  helpLabel?: string
  onHelp?: () => void
  trailing?: ReactNode
  merchantName?: string
  tagline?: string
  className?: string
}

function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean)
  return [words[0], words.length > 1 ? words[words.length - 1] : undefined]
    .filter((word): word is string => Boolean(word)).map(word => Array.from(word)[0]).join('').toUpperCase()
}

export function AppBar({ title, backLabel, onBack, language, languageLabel, onLanguageClick, helpLabel, onHelp, trailing, merchantName, tagline, className }: AppBarProps) {
  return (
    <header className={cn('safe-top flex min-h-[72px] items-center gap-2 border-b border-hairline bg-card px-3 py-2', className)}>
      {onBack && <div className="w-12 shrink-0">
          <button type="button" onClick={onBack} aria-label={backLabel} className="flex min-h-touch min-w-touch items-center justify-center rounded-chip text-navy">
            <ArrowLeft aria-hidden="true" className="h-icon w-icon" />
          </button>
      </div>}
      {merchantName && <span aria-hidden="true" className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-cyan-50 text-sm font-bold text-navy">{initials(merchantName)}</span>}
      <h1 className={cn('min-w-0 flex-1 text-base font-semibold text-navy', merchantName ? 'flex justify-center' : 'truncate')}>{title === 'Paytm Hisaab' ? <Logo withWordmark showMark={false} tagline={tagline} /> : <span className="inline-flex min-w-0 items-center gap-2">{!onBack && <Logo />}<span className="truncate">{title}</span></span>}</h1>
      {language && (
        <button type="button" onClick={onLanguageClick} aria-label={languageLabel ?? language} className="min-h-touch rounded-chip bg-cyan-50 px-3 text-sm font-semibold text-navy">
          {language}
        </button>
      )}
      {trailing}
      {onHelp && (
        <button type="button" onClick={onHelp} aria-label={helpLabel} className="flex min-h-touch min-w-touch items-center justify-center rounded-chip text-navy">
          <CircleHelp aria-hidden="true" className="h-icon w-icon" />
        </button>
      )}
    </header>
  )
}
