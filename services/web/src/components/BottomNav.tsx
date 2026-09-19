import type { ReactNode } from 'react'
import { cn } from './utils'

export interface BottomNavItem {
  id: string
  label: string
  icon: ReactNode
}

export interface BottomNavProps {
  items: BottomNavItem[]
  activeId: string
  onChange: (id: string) => void
  position?: 'fixed' | 'contained'
  ariaLabel: string
  className?: string
}

export function BottomNav({ items, activeId, onChange, position = 'fixed', ariaLabel, className }: BottomNavProps) {
  return (
    <nav aria-label={ariaLabel} className={cn('safe-bottom z-30 border-t border-hairline bg-card', position === 'fixed' ? 'fixed inset-x-0 bottom-0' : 'relative', className)}>
      <div className="mx-auto flex max-w-phone items-stretch justify-around gap-2 px-3 py-2">
        {items.map((item) => {
          const active = item.id === activeId
          return (
            <button key={item.id} type="button" onClick={() => onChange(item.id)} aria-current={active ? 'page' : undefined} className={cn('relative flex min-h-[64px] min-w-touch flex-1 flex-col items-center justify-center gap-1 rounded-card px-1 text-xs transition-colors duration-fast ease-out', active ? 'bg-cyan-50 font-bold text-navy' : 'font-medium text-muted')}>
              <span aria-hidden="true" className="[&>svg]:h-icon [&>svg]:w-icon">{item.icon}</span>
              <span className="max-w-full truncate">{item.label}</span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}
