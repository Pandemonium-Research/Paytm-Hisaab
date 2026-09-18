import type { ReactNode } from 'react'
import { cn } from './utils'

export interface TileGridItem {
  id: string
  label: string
  icon: ReactNode
  badge?: string
  disabled?: boolean
}

export interface TileGridProps {
  items: TileGridItem[]
  onSelect: (id: string) => void
  ariaLabel: string
  className?: string
}

export function TileGrid({ items, onSelect, ariaLabel, className }: TileGridProps) {
  return (
    <div role="group" aria-label={ariaLabel} className={cn('grid grid-cols-4 gap-x-2 gap-y-5', className)}>
      {items.map((item) => (
        <button key={item.id} type="button" disabled={item.disabled} onClick={() => onSelect(item.id)} className="relative flex min-h-[84px] min-w-0 flex-col items-center gap-2 rounded-card px-1 text-center text-xs font-medium text-ink disabled:opacity-45">
          <span className="flex h-icon-tile w-icon-tile items-center justify-center rounded-[14px] bg-cyan-50 text-navy [&>svg]:h-icon [&>svg]:w-icon" aria-hidden="true">{item.icon}</span>
          <span className="line-clamp-2">{item.label}</span>
          {item.badge && <span className="absolute right-0 top-0 rounded-chip bg-alert px-1.5 py-0.5 text-[10px] font-bold text-white">{item.badge}</span>}
        </button>
      ))}
    </div>
  )
}
