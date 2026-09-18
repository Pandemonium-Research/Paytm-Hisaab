import { X } from 'lucide-react'
import type { ReactElement, ReactNode } from 'react'
import { Drawer } from 'vaul'

export interface BottomSheetProps {
  trigger: ReactElement
  title: string
  description?: string
  closeLabel: string
  children: ReactNode
  open?: boolean
  onOpenChange?: (open: boolean) => void
}

export function BottomSheet({ trigger, title, description, closeLabel, children, open, onOpenChange }: BottomSheetProps) {
  return (
    <Drawer.Root open={open} onOpenChange={onOpenChange}>
      <Drawer.Trigger asChild>{trigger}</Drawer.Trigger>
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-ink/45" />
        <Drawer.Content className="safe-bottom fixed inset-x-0 bottom-0 z-50 mx-auto max-h-[88dvh] max-w-phone overflow-y-auto rounded-t-sheet bg-card px-4 pb-5 pt-3 outline-none">
          <div aria-hidden="true" className="mx-auto mb-3 h-1 w-10 rounded-chip bg-hairline" />
          <div className="flex items-start gap-3">
            <div className="min-w-0 flex-1">
              <Drawer.Title className="text-lg font-semibold text-navy">{title}</Drawer.Title>
              {description && <Drawer.Description className="mt-1 text-sm text-muted">{description}</Drawer.Description>}
            </div>
            <Drawer.Close aria-label={closeLabel} className="flex min-h-touch min-w-touch items-center justify-center rounded-chip text-muted">
              <X aria-hidden="true" className="h-icon w-icon" />
            </Drawer.Close>
          </div>
          <div className="mt-4">{children}</div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}
