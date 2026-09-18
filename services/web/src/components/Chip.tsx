import type { ButtonHTMLAttributes } from 'react'
import { cn } from './utils'

export interface ChipProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'aria-pressed'> {
  selected?: boolean
}

export function Chip({ selected = false, className, children, ...props }: ChipProps) {
  return (
    <button type="button" aria-pressed={selected} className={cn('min-h-touch rounded-chip border px-4 py-2 text-sm font-semibold transition-colors duration-fast ease-out', selected ? 'border-cyan bg-cyan-50 text-navy' : 'border-hairline bg-card text-ink', className)} {...props}>
      {children}
    </button>
  )
}

export interface ChipOption<T extends string> {
  value: T
  label: string
  disabled?: boolean
}

export interface ChipGroupProps<T extends string> {
  label: string
  options: ChipOption<T>[]
  value?: T
  onChange: (value: T) => void
  className?: string
}

export function ChipGroup<T extends string>({ label, options, value, onChange, className }: ChipGroupProps<T>) {
  return (
    <div role="group" aria-label={label} className={cn('flex flex-wrap gap-2', className)}>
      {options.map((option) => <Chip key={option.value} selected={option.value === value} disabled={option.disabled} onClick={() => onChange(option.value)}>{option.label}</Chip>)}
    </div>
  )
}
