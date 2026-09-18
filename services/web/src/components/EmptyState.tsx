import type { ReactNode } from 'react'

export interface EmptyStateProps {
  icon: ReactNode
  title: string
  description: string
  actionLabel?: string
  onAction?: () => void
}

export function EmptyState({ icon, title, description, actionLabel, onAction }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center px-6 py-10 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-card bg-cyan-50 text-navy [&>svg]:h-7 [&>svg]:w-7" aria-hidden="true">{icon}</div>
      <h3 className="mt-4 text-base font-semibold text-navy">{title}</h3>
      <p className="mt-1 max-w-[280px] text-sm text-muted">{description}</p>
      {actionLabel && onAction && <button type="button" onClick={onAction} className="mt-4 min-h-touch rounded-chip bg-cyan px-5 text-sm font-semibold text-navy">{actionLabel}</button>}
    </div>
  )
}
