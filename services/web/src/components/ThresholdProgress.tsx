import { cn } from './utils'

export interface ThresholdProgressProps {
  current: number
  threshold: number
  maximum?: number
  currentLabel: string
  thresholdLabel: string
  projectedLabel?: string
  projectedDate?: string
  detailLabel?: string
  showThresholdMarker?: boolean
  fillTone?: 'cyan' | 'credit' | 'alert'
  className?: string
}

const fillClasses = { cyan: 'bg-cyan', credit: 'bg-credit', alert: 'bg-alert' }

export function ThresholdProgress({ current, threshold, maximum = threshold * 1.15, currentLabel, thresholdLabel, projectedLabel, projectedDate, detailLabel, showThresholdMarker = true, fillTone = 'cyan', className }: ThresholdProgressProps) {
  const safeMaximum = Math.max(maximum, threshold, 1)
  const fill = Math.min(100, Math.max(0, (current / safeMaximum) * 100))
  const marker = Math.min(100, Math.max(0, (threshold / safeMaximum) * 100))
  return (
    <div className={className}>
      <div className="flex items-end justify-between gap-3">
        <p className="amount-numerals text-lg font-bold text-navy">{currentLabel}</p>
        {detailLabel ? <p className="max-w-[55%] text-right text-xs font-medium text-muted">{detailLabel}</p> : projectedLabel && <p className="text-right text-xs text-muted">{projectedLabel}<br />{projectedDate && <span className="font-semibold text-notice">{projectedDate}</span>}</p>}
      </div>
      <div className={cn('relative h-2 rounded-chip bg-hairline', showThresholdMarker ? 'mt-7' : 'mt-4')} role="progressbar" aria-valuemin={0} aria-valuemax={threshold} aria-valuenow={Math.min(current, threshold)}>
        <div className={`h-full rounded-chip ${fillClasses[fillTone]} transition-[width] duration-standard ease-out`} style={{ width: `${fill}%` }} />
        {showThresholdMarker && <div className="absolute -top-2 h-6 w-0.5 bg-navy" style={{ left: `${marker}%` }}>
          <span className="absolute bottom-full left-1/2 mb-1 -translate-x-1/2 whitespace-nowrap text-xs font-semibold text-navy">{thresholdLabel}</span>
        </div>}
      </div>
    </div>
  )
}
