import { cn } from './utils'

export interface TierSegment {
  tier: 1 | 2 | 3 | 4
  label: string
  value: number
}

export interface TierBarProps {
  segments: TierSegment[]
  ariaLabel: string
  showLegend?: boolean
  className?: string
}

const tierBackgrounds = { 1: 'bg-tier1', 2: 'bg-tier2', 3: 'bg-tier3', 4: 'bg-tier4' }

export function TierBar({ segments, ariaLabel, showLegend = true, className }: TierBarProps) {
  const total = segments.reduce((sum, segment) => sum + Math.max(0, segment.value), 0)
  return (
    <div className={className}>
      <div className="flex h-3 w-full overflow-hidden rounded-chip bg-hairline" role="img" aria-label={ariaLabel}>
        {segments.map((segment) => <span key={segment.tier} className={cn('h-full transition-[width] duration-standard ease-out', tierBackgrounds[segment.tier])} style={{ width: `${total ? (Math.max(0, segment.value) / total) * 100 : 0}%` }} />)}
      </div>
      {showLegend && (
        <ul className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2">
          {segments.map((segment) => (
            <li key={segment.tier} className="flex items-center gap-2 text-xs text-muted">
              <span aria-hidden="true" className={cn('h-2.5 w-2.5 rounded-full', tierBackgrounds[segment.tier])} />
              <span className="flex-1 truncate">{segment.label}</span>
              <span className="amount-numerals font-semibold text-ink">{total ? Math.round((segment.value / total) * 100) : 0}%</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
