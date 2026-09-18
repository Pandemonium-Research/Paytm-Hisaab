import type { ReactNode } from 'react'
import { cn } from './utils'

export interface PhoneFrameProps {
  children: ReactNode
  label: string
  className?: string
}

export function PhoneFrame({ children, label, className }: PhoneFrameProps) {
  return (
    <div aria-label={label} className={cn('relative mx-auto h-phone w-full max-w-phone overflow-hidden bg-bg sm:rounded-[36px] sm:border-[8px] sm:border-ink sm:shadow-card', className)}>
      <div aria-hidden="true" className="absolute left-1/2 top-2 z-50 hidden h-5 w-24 -translate-x-1/2 rounded-chip bg-ink sm:block" />
      <div className="scrollbar-none h-full overflow-y-auto sm:pt-5">{children}</div>
    </div>
  )
}
