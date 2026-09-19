import { cn } from './utils'

export interface LogoProps {
  size?: number
  withWordmark?: boolean
  className?: string
}

export function Logo({ size = 28, withWordmark = false, className }: LogoProps) {
  return (
    <span className={cn('inline-flex min-w-0 items-center gap-2', className)}>
      <svg aria-hidden="true" viewBox="0 0 64 64" width={size} height={size} className="shrink-0">
        <rect width="64" height="64" rx="14" className="fill-navy [.bg-navy_&]:fill-card" />
        <path d="M17 15h9v13h12V15h9v34h-9V36H26v13h-9z" className="fill-cyan [.bg-navy_&]:fill-navy" />
      </svg>
      {withWordmark && <span className="truncate text-lg font-semibold tracking-tight text-navy [.bg-navy_&]:text-card">Paytm Hisaab</span>}
    </span>
  )
}
