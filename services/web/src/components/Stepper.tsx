import { Check } from 'lucide-react'
import { cn } from './utils'

export type StepStatus = 'complete' | 'current' | 'upcoming'

export interface StepperStep {
  id: string
  title: string
  description?: string
  meta?: string
  status: StepStatus
}

export interface StepperProps {
  steps: StepperStep[]
  ariaLabel: string
  className?: string
}

export function Stepper({ steps, ariaLabel, className }: StepperProps) {
  return (
    <ol aria-label={ariaLabel} className={cn('space-y-0', className)}>
      {steps.map((step, index) => (
        <li key={step.id} aria-current={step.status === 'current' ? 'step' : undefined} className="grid grid-cols-[32px_1fr] gap-3">
          <div className="flex flex-col items-center">
            <span className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 text-xs font-bold', step.status === 'complete' && 'border-credit bg-credit text-white', step.status === 'current' && 'border-cyan bg-cyan text-navy ring-4 ring-cyan-50', step.status === 'upcoming' && 'border-hairline bg-card text-muted')}>
              {step.status === 'complete' ? <Check aria-hidden="true" className="h-4 w-4 animate-tick" /> : index + 1}
            </span>
            {index < steps.length - 1 && <span className={cn('min-h-10 w-0.5 flex-1', step.status === 'complete' ? 'bg-credit' : 'bg-hairline')} />}
          </div>
          <div className="pb-5 pt-1">
            <div className="flex items-baseline justify-between gap-2">
              <h3 className={cn('text-sm font-semibold', step.status === 'upcoming' ? 'text-muted' : 'text-ink')}>{step.title}</h3>
              {step.meta && <span className="shrink-0 text-xs text-muted">{step.meta}</span>}
            </div>
            {step.description && <p className="mt-1 text-xs text-muted">{step.description}</p>}
          </div>
        </li>
      ))}
    </ol>
  )
}
