import { AnimatePresence, motion } from 'framer-motion'
import { AlertCircle, CheckCircle2, Info } from 'lucide-react'
import { cn } from './utils'

export interface SnackbarProps {
  visible: boolean
  message: string
  tone?: 'info' | 'success' | 'error'
  actionLabel?: string
  onAction?: () => void
  className?: string
}

const toneClasses = { info: 'bg-ink', success: 'bg-tier1', error: 'bg-alert' }
const icons = { info: Info, success: CheckCircle2, error: AlertCircle }

export function Snackbar({ visible, message, tone = 'info', actionLabel, onAction, className }: SnackbarProps) {
  const Icon = icons[tone]
  return (
    <AnimatePresence>
      {visible && (
        <motion.div role={tone === 'error' ? 'alert' : 'status'} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }} transition={{ duration: 0.18, ease: 'easeOut' }} className={cn('flex min-h-touch items-center gap-3 rounded-card px-4 py-3 text-sm text-white shadow-card', toneClasses[tone], className)}>
          <Icon aria-hidden="true" className="h-5 w-5 shrink-0" />
          <span className="flex-1">{message}</span>
          {actionLabel && onAction && <button type="button" onClick={onAction} className="min-h-touch rounded-chip px-2 font-bold text-white underline underline-offset-2">{actionLabel}</button>}
        </motion.div>
      )}
    </AnimatePresence>
  )
}
