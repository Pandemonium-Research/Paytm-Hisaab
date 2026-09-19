import { useCallback, useEffect, useRef, useState } from 'react'
import { LoaderCircle } from 'lucide-react'
import { AppBar, Card, Skeleton, Snackbar } from '../components'
import { adminApi, api, forMerchant, merchant, post, railsApi } from '../api'
import type { AppConfig, Home, MerchantCase, RailsEventsResponse, SimClockResponse, SimReplayResponse, SimResetResponse } from '../api'

type HealthState = { ok: boolean | null; checkedAt: Date | null; detail?: string }
type LogEntry = { id: string; at: Date; action: string; message: string; error: boolean }
type DemoEvents = { events: Record<string, unknown>[] }

const jumpPresets = [
  { label: '31 Jan 2026', instant: '2026-01-31T00:00:00+05:30' },
  { label: '10 Mar 2026 02:00', instant: '2026-03-10T02:00:00+05:30' },
  { label: '24 Mar 2026 09:25', instant: '2026-03-24T09:25:00+05:30' },
  { label: '20 Aug 2026', instant: '2026-08-20T00:00:00+05:30' }
]

const primaryButton = 'min-h-[56px] w-full rounded-card bg-navy px-4 py-3 text-base font-bold text-white disabled:cursor-not-allowed disabled:opacity-50'
const secondaryButton = 'min-h-[56px] w-full rounded-card bg-cyan px-4 py-3 text-base font-bold text-navy disabled:cursor-not-allowed disabled:opacity-50'
const nightlyLockKey = 'hisaab-nightly-triggered'
const nightlyMinimumRunMs = 60000
// WF10 acknowledges on receipt, so the page cannot see the run end. Hold the lock well past the
// measured ~55 s instead of until reset: a second concurrent run poisons the window, but making
// a rehearsal reset the whole demo to run nightly twice is its own trap.
const nightlyLockMs = 180000

function messageOf(error: unknown) {
  return error instanceof Error ? error.message : String(error)
}

function formatCheckTime(value: Date | null) {
  return value ? value.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : 'not checked'
}

async function fetchJson<T>(url: string, options: RequestInit = {}): Promise<T | null> {
  const response = await fetch(url, { ...options, cache: 'no-store' })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed (${response.status})`)
  }
  const text = await response.text()
  return text ? JSON.parse(text) as T : null
}

export function DemoScreen() {
  const [health, setHealth] = useState<Record<'core' | 'n8n', HealthState>>({
    core: { ok: null, checkedAt: null }, n8n: { ok: null, checkedAt: null }
  })
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [activeAction, setActiveAction] = useState<string | null>(null)
  const [nightlyStartedAt, setNightlyStartedAt] = useState<number | null>(null)
  const [nightlyLocked, setNightlyLocked] = useState(() => {
    const until = Number(sessionStorage.getItem(nightlyLockKey))
    return Number.isFinite(until) && until > Date.now()
  })
  const [elapsed, setElapsed] = useState(0)
  const [resetArmed, setResetArmed] = useState(false)
  const [latestResult, setLatestResult] = useState<string | null>(null)
  const nightlyInFlight = useRef(false)

  const addLog = useCallback((action: string, message: string, error = false) => {
    setLogs(current => [{ id: crypto.randomUUID(), at: new Date(), action, message, error }, ...current])
    setLatestResult(message)
  }, [])

  const checkHealth = useCallback(async () => {
    const checkedAt = new Date()
    const core = api<AppConfig>('/config').then(config => {
      if (config.live !== false) throw new Error('Core is reachable but live mode is enabled')
      return { ok: true, checkedAt } satisfies HealthState
    }).catch(error => ({ ok: false, checkedAt, detail: messageOf(error) }) satisfies HealthState)
    const n8n = (async (): Promise<HealthState> => {
      const controller = new AbortController()
      const timeout = window.setTimeout(() => controller.abort(), 5000)
      try {
        // no-cors yields an opaque response, so a resolved fetch proves reachability only.
        await fetch('http://localhost:5678/healthz', { mode: 'no-cors', cache: 'no-store', signal: controller.signal })
        return { ok: true, checkedAt }
      } catch (error) {
        return { ok: false, checkedAt, detail: messageOf(error) }
      } finally {
        window.clearTimeout(timeout)
      }
    })()
    const [coreState, n8nState] = await Promise.all([core, n8n])
    setHealth({ core: coreState, n8n: n8nState })
  }, [])

  useEffect(() => {
    void checkHealth()
    const interval = window.setInterval(() => void checkHealth(), 10000)
    return () => window.clearInterval(interval)
  }, [checkHealth])

  useEffect(() => {
    if (nightlyStartedAt === null) return
    setElapsed(Math.floor((Date.now() - nightlyStartedAt) / 1000))
    const interval = window.setInterval(() => setElapsed(Math.floor((Date.now() - nightlyStartedAt) / 1000)), 1000)
    return () => window.clearInterval(interval)
  }, [nightlyStartedAt])

  async function jumpTo(label: string, instant: string) {
    if (activeAction) return
    const action = `Jump to ${label}`
    setResetArmed(false); setActiveAction(action)
    try {
      await adminApi<SimClockResponse>('/sim/clock', post({ sim_at: instant }))
      const replay = await adminApi<SimReplayResponse>('/sim/replay', post({ split: 'demo', until: instant }))
      addLog(action, `sim_at ${replay.sim_at}; transactions_replayed ${replay.transactions_replayed}`)
    } catch (error) {
      addLog(action, messageOf(error), true)
    } finally {
      setActiveAction(null)
    }
  }

  async function runNightly() {
    if (nightlyInFlight.current || nightlyLocked) return
    nightlyInFlight.current = true
    const startedAt = Date.now()
    sessionStorage.setItem(nightlyLockKey, String(startedAt + nightlyLockMs))
    setNightlyLocked(true)
    window.setTimeout(() => { sessionStorage.removeItem(nightlyLockKey); setNightlyLocked(false) }, nightlyLockMs)
    setResetArmed(false); setActiveAction('Run nightly'); setElapsed(0); setNightlyStartedAt(startedAt)
    try {
      const home = await api<Home>(forMerchant('/app/home'))
      const response = await fetchJson<unknown>('http://localhost:5678/webhook/hisaab/wf10-nightly', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-N8N-Webhook-Secret': import.meta.env.VITE_N8N_WEBHOOK_SECRET || 'dev-webhook-secret' },
        body: JSON.stringify({ merchant_id: merchant, as_of: home.as_of, mode: 'live', channel: 'app', window_from: '2026-03-08', window_to: '2026-03-10' })
      })
      // WF10 acknowledges on receipt, not completion. Keep the visible running state for its
      // measured duration, and retain the lock until reset so an early ack cannot enable overlap.
      const remaining = nightlyMinimumRunMs - (Date.now() - startedAt)
      if (remaining > 0) await new Promise(resolve => window.setTimeout(resolve, remaining))
      addLog('Run nightly', response === null ? 'Trigger accepted; locked for three minutes' : `Trigger accepted; locked for three minutes · ${JSON.stringify(response)}`)
    } catch (error) {
      sessionStorage.removeItem(nightlyLockKey)
      setNightlyLocked(false)
      addLog('Run nightly', messageOf(error), true)
    } finally {
      nightlyInFlight.current = false
      setNightlyStartedAt(null); setActiveAction(null)
    }
  }

  async function startDeclinesAndLien() {
    if (activeAction) return
    const action = 'Start declines and lien'
    setResetArmed(false); setActiveAction(action)
    try {
      const fixture = await fetchJson<DemoEvents>('/demo-events.json')
      if (!fixture || !Array.isArray(fixture.events) || fixture.events.length !== 4) throw new Error('Demo event fixture must contain exactly four events')
      const eventTimes = fixture.events.map(event => event.ts).filter((ts): ts is string => typeof ts === 'string').sort()
      if (eventTimes.length !== fixture.events.length) throw new Error('Every demo event must have a timestamp')
      // Core refuses future observations. Move business time through the complete staged burst
      // before the one idempotent rails ingest, so this works from the 09:25 jump preset.
      await adminApi<SimClockResponse>('/sim/clock', post({ sim_at: eventTimes[eventTimes.length - 1] }))
      const response = await railsApi<RailsEventsResponse>('/rails/events', post(fixture))
      if (response.opened_case_ids.length) {
        addLog(action, `accepted ${response.accepted}; opened ${response.opened_case_ids.join(', ')}`)
      } else {
        // Rails ingest is idempotent, so running this twice accepts nothing. That is not a dead
        // button, and "accepted 0" alone reads like one on stage: name the case already open.
        const open = await api<{ items: MerchantCase[] }>(forMerchant('/app/cases'))
        const freeze = open.items.find(row => row.case_type === 'freeze')
        addLog(action, freeze
          ? `accepted ${response.accepted}; already ingested · ${freeze.case_id} is ${freeze.status.replaceAll('_', ' ')}`
          : `accepted ${response.accepted}; no case opened`, !freeze)
      }
    } catch (error) {
      addLog(action, messageOf(error), true)
    } finally {
      setActiveAction(null)
    }
  }

  async function resetDemo() {
    if (activeAction) return
    const action = 'Reset sim clock and demo state'
    setActiveAction(action)
    try {
      const response = await adminApi<SimResetResponse>('/sim/reset', post({ split: 'demo' }))
      sessionStorage.removeItem(nightlyLockKey)
      setNightlyLocked(false)
      addLog(action, `sim_at ${response.sim_at}`)
    } catch (error) {
      addLog(action, messageOf(error), true)
    } finally {
      setResetArmed(false); setActiveAction(null)
    }
  }

  const nightlyRunning = nightlyStartedAt !== null
  return <main className="mx-auto min-h-dvh max-w-phone overflow-x-hidden bg-bg pb-10">
    <AppBar title="Demo remote" />
    <div className="space-y-5 p-4">
      <section aria-labelledby="health-heading">
        <h2 id="health-heading" className="mb-2 text-sm font-semibold text-navy">Health</h2>
        <Card className="space-y-3">
          {(['core', 'n8n'] as const).map(name => <div key={name} className="flex min-w-0 items-center gap-3">
            {health[name].ok === null ? <Skeleton className="h-3 w-3 shrink-0 rounded-chip" /> : <span aria-label={health[name].ok ? 'healthy' : 'unhealthy'} className={`h-3 w-3 shrink-0 rounded-chip ${health[name].ok ? 'bg-credit' : 'bg-alert'}`} />}
            <div className="min-w-0 flex-1"><p className="text-sm font-semibold">{name}</p><p className="break-words text-xs text-muted">Last check {formatCheckTime(health[name].checkedAt)}{health[name].detail ? ` · ${health[name].detail}` : ''}</p></div>
          </div>)}
        </Card>
      </section>

      <section aria-labelledby="jump-heading">
        <h2 id="jump-heading" className="mb-2 text-sm font-semibold text-navy">Jump to</h2>
        <div className="space-y-3">{jumpPresets.map(preset => <button type="button" key={preset.instant} className={primaryButton} disabled={activeAction !== null} onClick={() => void jumpTo(preset.label, preset.instant)}>{activeAction === `Jump to ${preset.label}` ? 'Jumping and replaying…' : preset.label}</button>)}</div>
      </section>

      <section aria-labelledby="actions-heading" className="space-y-3">
        <h2 id="actions-heading" className="text-sm font-semibold text-navy">Run demo actions</h2>
        <button type="button" className={secondaryButton} disabled={nightlyLocked || activeAction !== null} onClick={() => void runNightly()}>{nightlyRunning ? <span className="inline-flex items-center gap-2"><LoaderCircle aria-hidden="true" className="h-5 w-5 animate-spin" />Running nightly · {elapsed} s</span> : nightlyLocked ? 'Nightly running · locked for 3 min' : 'Run nightly'}</button>
        <p className="text-xs text-muted">WF10 usually takes about 55 seconds. After one trigger this control locks for three minutes, so two runs cannot overlap.</p>
        <button type="button" className={secondaryButton} disabled={activeAction !== null} onClick={() => void startDeclinesAndLien()}>{activeAction === 'Start declines and lien' ? 'Starting…' : 'Start declines and lien'}</button>
      </section>

      {latestResult && <Snackbar visible message={latestResult} tone={logs[0]?.error ? 'error' : 'success'} className="min-w-0 break-all" />}

      <section aria-labelledby="reset-heading" className="border-t border-hairline pt-5">
        <h2 id="reset-heading" className="mb-2 text-sm font-semibold text-alert">Reset</h2>
        <button type="button" className={`min-h-[64px] w-full rounded-card px-4 py-3 text-base font-bold disabled:opacity-50 ${resetArmed ? 'bg-alert text-white' : 'border-2 border-alert bg-card text-alert'}`} disabled={activeAction !== null} onClick={() => resetArmed ? void resetDemo() : setResetArmed(true)}>{activeAction === 'Reset sim clock and demo state' ? 'Resetting…' : resetArmed ? 'Tap again to confirm reset' : 'Reset sim clock and demo state'}</button>
        {resetArmed && <button type="button" className="mt-2 min-h-touch w-full rounded-chip text-sm font-semibold text-muted" onClick={() => setResetArmed(false)}>Cancel reset</button>}
      </section>

      <section aria-labelledby="log-heading">
        <h2 id="log-heading" className="mb-2 text-sm font-semibold text-navy">Action log</h2>
        <Card padding="compact">
          {!logs.length ? <p className="p-1 text-sm text-muted">Actions and errors will appear here.</p> : <ol className="divide-y divide-hairline">{logs.map(entry => <li key={entry.id} className="break-words px-1 py-3">
            <div className="flex items-start justify-between gap-2"><span className={`text-sm font-semibold ${entry.error ? 'text-alert' : 'text-navy'}`}>{entry.action}</span><time className="shrink-0 text-xs text-muted">{entry.at.toLocaleTimeString('en-IN')}</time></div>
            <p role={entry.error ? 'alert' : 'status'} className={`mt-1 text-sm ${entry.error ? 'text-alert' : 'text-ink'}`}>{entry.message}</p>
          </li>)}</ol>}
        </Card>
      </section>
    </div>
  </main>
}
