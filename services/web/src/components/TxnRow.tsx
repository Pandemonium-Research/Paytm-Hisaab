import type { ReactNode } from 'react'
import { AmountText } from './AmountText'
import { cn } from './utils'

export type Tier = 1 | 2 | 3 | 4

export interface TxnRowProps {
  name: string
  time: string
  /** Preformatted by core; see AmountText. */
  amount: string
  channelIcon: ReactNode
  channelLabel: string
  label: string
  tier: Tier
  tierLabel: string
  initial?: string
  onClick?: () => void
  className?: string
}

const tierClasses: Record<Tier, string> = { 1: 'bg-tier1', 2: 'bg-tier2', 3: 'bg-tier3', 4: 'bg-tier4' }

export function TxnRow({ name, time, amount, channelIcon, channelLabel, label, tier, tierLabel, initial = name.charAt(0), onClick, className }: TxnRowProps) {
  const body = (
    <>
      <span className="flex h-icon-tile w-icon-tile shrink-0 items-center justify-center rounded-full bg-cyan-50 text-base font-bold text-navy" aria-hidden="true">{initial}</span>
      <span className="min-w-0 flex-1 text-left">
        <span className="block truncate text-sm font-semibold text-ink">{name}</span>
        <span className="mt-0.5 flex items-center gap-1.5 text-xs text-muted">
          <span className="[&>svg]:h-3.5 [&>svg]:w-3.5" aria-label={channelLabel}>{channelIcon}</span>
          <span>{time}</span>
        </span>
      </span>
      <span className="shrink-0 text-right">
        <AmountText amount={amount} credit prefix="+" />
        <span className="mt-1 flex items-center justify-end gap-1.5">
          <span className={cn('h-2 w-2 rounded-full', tierClasses[tier])} aria-label={tierLabel} />
          <span className="max-w-[94px] truncate rounded-chip bg-bg px-2 py-0.5 text-xs text-muted">{label}</span>
        </span>
      </span>
    </>
  )

  const classes = cn('flex min-h-[72px] w-full items-center gap-3 border-b border-hairline bg-card px-4 py-3 last:border-b-0', className)
  return onClick ? <button type="button" onClick={onClick} className={classes}>{body}</button> : <div className={classes}>{body}</div>
}
