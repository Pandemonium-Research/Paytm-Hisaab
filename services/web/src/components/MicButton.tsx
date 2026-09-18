import { Mic } from 'lucide-react'
import { useRef, useState, type PointerEvent } from 'react'
import { cn } from './utils'

export interface MicButtonProps {
  label: string
  holdingLabel: string
  onHoldStart: () => void
  onHoldEnd: () => void
  disabled?: boolean
  className?: string
}

export function MicButton({ label, holdingLabel, onHoldStart, onHoldEnd, disabled = false, className }: MicButtonProps) {
  const [holding, setHolding] = useState(false)
  const active = useRef(false)

  function start(event: PointerEvent<HTMLButtonElement>) {
    if (disabled) return
    event.currentTarget.setPointerCapture(event.pointerId)
    active.current = true
    setHolding(true)
    onHoldStart()
  }

  function end() {
    if (!active.current) return
    active.current = false
    setHolding(false)
    onHoldEnd()
  }

  return (
    <button type="button" disabled={disabled} onPointerDown={start} onPointerUp={end} onPointerCancel={end} onLostPointerCapture={end} aria-pressed={holding} aria-label={holding ? holdingLabel : label} className={cn('flex min-h-touch items-center justify-center gap-3 rounded-chip px-5 text-sm font-semibold transition-colors duration-standard ease-out', holding ? 'bg-alert text-white' : 'bg-cyan text-navy', className)}>
      <Mic aria-hidden="true" className="h-icon w-icon" />
      <span>{holding ? holdingLabel : label}</span>
      <span aria-hidden="true" className="flex h-6 items-center gap-0.5">
        {[10, 18, 24, 16, 9].map((height, index) => <span key={index} className={cn('w-0.5 rounded-chip bg-current transition-all duration-fast', holding && 'animate-pulse')} style={{ height: holding ? height : 5 }} />)}
      </span>
    </button>
  )
}
