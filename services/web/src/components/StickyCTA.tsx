import type { ButtonHTMLAttributes } from 'react'
import { cn } from './utils'

export interface StickyCTAProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string
  secondaryLabel?: string
  onSecondary?: () => void
  position?: 'fixed' | 'contained'
}

export function StickyCTA({ label, secondaryLabel, onSecondary, position = 'fixed', className, disabled, ...props }: StickyCTAProps) {
  return (
    <div className={cn('safe-bottom z-20 border-t border-hairline bg-card/95 p-3 backdrop-blur', position === 'fixed' ? 'fixed inset-x-0 bottom-0' : 'relative', className)}>
      <div className="mx-auto flex max-w-phone gap-2">
        {secondaryLabel && onSecondary && <button type="button" onClick={onSecondary} className="min-h-touch flex-1 rounded-chip border border-cyan bg-card px-4 text-sm font-semibold text-navy">{secondaryLabel}</button>}
        <button type="button" disabled={disabled} className="min-h-touch flex-[2] rounded-chip bg-cyan px-5 text-sm font-bold text-navy transition-colors duration-fast ease-out disabled:bg-hairline disabled:text-muted" {...props}>{label}</button>
      </div>
    </div>
  )
}
