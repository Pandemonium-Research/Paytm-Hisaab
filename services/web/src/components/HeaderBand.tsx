import type { ReactNode } from 'react'
import { AmountText } from './AmountText'
import { cn } from './utils'

export interface HeaderBandProps {
  businessName: string
  collectionLabel: string
  /** Preformatted by core; see AmountText. */
  amount: string
  paymentSummary?: string
  wordmark?: ReactNode
  className?: string
}

export function HeaderBand({ businessName, collectionLabel, amount, paymentSummary, wordmark, className }: HeaderBandProps) {
  return (
    <section className={cn('safe-top rounded-b-sheet bg-navy px-4 pb-6 pt-4 text-white', className)}>
      {wordmark && <div className="mb-5">{wordmark}</div>}
      <p className="text-sm text-white/75">{businessName}</p>
      <div className="mt-2 flex flex-wrap items-end justify-between gap-2">
        <div>
          <p className="text-xs text-white/75">{collectionLabel}</p>
          <AmountText amount={amount} size="large" className="text-white" />
        </div>
        {paymentSummary && <p className="pb-1 text-sm font-medium text-white/90">{paymentSummary}</p>}
      </div>
    </section>
  )
}
