import type { HTMLAttributes } from 'react'
import { cn } from './utils'

export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden="true" className={cn('animate-shimmer rounded-chip bg-[linear-gradient(90deg,#E6ECF2_25%,#F5F7FA_50%,#E6ECF2_75%)] bg-[length:200%_100%]', className)} {...props} />
}
