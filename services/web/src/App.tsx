import { BriefcaseBusiness } from 'lucide-react'
import { Card } from './components'
import { Gallery } from './gallery/Gallery'

function FoundationShell() {
  return (
    <main className="safe-top safe-bottom flex min-h-dvh items-center justify-center bg-bg p-4">
      <Card className="w-full max-w-[360px] text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-[14px] bg-cyan-50 text-navy"><BriefcaseBusiness aria-hidden="true" className="h-icon w-icon" /></div>
        <p className="mt-4 text-lg font-bold tracking-tight"><span className="text-navy">Paytm</span> <span className="text-cyan">Hisaab</span></p>
        <h1 className="mt-2 text-base font-semibold text-ink">PWA foundation is ready</h1>
        <p className="mt-1 text-sm text-muted">Product screens will be added in a later milestone.</p>
        <a href="/__gallery" className="mt-5 inline-flex min-h-touch items-center rounded-chip bg-cyan px-5 text-sm font-bold text-navy">Open component gallery</a>
      </Card>
    </main>
  )
}

export default function App() {
  return window.location.pathname === '/__gallery' || window.location.pathname === '/__gallery/' ? <Gallery /> : <FoundationShell />
}
