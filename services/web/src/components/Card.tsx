import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from './utils'

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
  padding?: 'none' | 'compact' | 'default'
}

const paddingClasses = { none: '', compact: 'p-3', default: 'p-4' }

export function Card({ children, className, padding = 'default', ...props }: CardProps) {
  return (
    <div className={cn('rounded-card bg-card shadow-card', paddingClasses[padding], className)} {...props}>
      {children}
    </div>
  )
}
