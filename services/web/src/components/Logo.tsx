import { cn } from './utils'

export interface LogoProps {
  size?: number
  withWordmark?: boolean
  showMark?: boolean
  tagline?: string
  className?: string
}

export function Logo({ size = 28, withWordmark = false, showMark = true, tagline, className }: LogoProps) {
  return (
    <span className={cn('inline-flex min-w-0 items-center gap-2', className)}>
      {showMark && <svg aria-hidden="true" viewBox="0 0 64 64" width={size} height={size} className="shrink-0">
        <rect width="64" height="64" rx="14" className="fill-navy [.bg-navy_&]:fill-card" />
        <path d="M17 15h9v13h12V15h9v34h-9V36H26v13h-9z" className="fill-cyan [.bg-navy_&]:fill-navy" />
      </svg>}
      {withWordmark && <span className="flex min-w-0 flex-col items-center text-center">
        <span className="whitespace-nowrap text-lg font-bold tracking-tight [.bg-navy_&]:text-card"><span className="text-navy [.bg-navy_&]:text-card">Pay</span><span className="text-cyan">tm</span> <span className="text-navy [.bg-navy_&]:text-card">Hisaab</span></span>
        {tagline && <span aria-hidden="true" className="mt-0.5 text-[10px] leading-3 text-muted [.bg-navy_&]:text-card">{tagline}</span>}
      </span>}
    </span>
  )
}
