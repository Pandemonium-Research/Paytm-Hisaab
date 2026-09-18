import type { HTMLAttributes } from 'react'
import { cn } from './utils'

export interface AmountTextProps extends Omit<HTMLAttributes<HTMLSpanElement>, 'children'> {
  /**
   * Already formatted by core, e.g. `₹4,200`, `₹42.2 L`, `₹1.2 Cr`. The phone never formats a number
   * (services/core/CONTRACTS.md, Lane B, 1.6): core owns per-locale formatting, so the figure on screen always matches the
   * figure in the evidence pack.
   */
  amount: string
  credit?: boolean
  prefix?: string
  size?: 'small' | 'default' | 'large'
}

const sizeClasses = { small: 'text-sm', default: 'text-base', large: 'text-xl' }

export function AmountText({ amount, credit = false, prefix, size = 'default', className, ...props }: AmountTextProps) {
  return (
    <span className={cn('amount-numerals font-bold', sizeClasses[size], credit ? 'text-credit' : 'text-ink', className)} {...props}>
      {prefix}{amount}
    </span>
  )
}
