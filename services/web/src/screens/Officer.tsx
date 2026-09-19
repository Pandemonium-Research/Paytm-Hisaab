import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Clock3, ShieldCheck } from 'lucide-react'
import { AmountText, AppBar, Card, EmptyState, Skeleton, StickyCTA, TierBar, TxnRow } from '../components'
import { api, downloadPack, forMerchant, post } from '../api'
import type { FreezePack, Home, OfficerCase, OfficerCaseRow } from '../api'
import { Notice } from './Merchant'

export function OfficerScreens({ path, navigate }: { path: string; navigate: (path: string) => void }) {
  const caseId = path.startsWith('/officer/cases/') ? decodeURIComponent(path.slice('/officer/cases/'.length)) : null
  return <main className="mx-auto min-h-dvh max-w-phone overflow-x-hidden bg-bg pb-32">
    <AppBar title={caseId ? 'Review evidence pack' : 'Officer queue'} onBack={caseId ? () => navigate('/officer') : undefined} backLabel="Officer queue" />
    {caseId ? <Case caseId={caseId} /> : <Queue navigate={navigate} />}
  </main>
}
function Queue({ navigate }: { navigate: (path: string) => void }) {
  const queue = useQuery({ queryKey: ['officer-queue'], queryFn: () => api<{ items: OfficerCaseRow[] }>('/app/officer/queue', {}, true), refetchInterval: 3000 })
  if (queue.isPending) return <div className="p-4"><Skeleton className="h-48" /></div>
  if (queue.error) return <Notice error={queue.error} retry={() => void queue.refetch()} />
  if (!queue.data.items.length) return <EmptyState icon={<ShieldCheck />} title="Queue is clear" description="New cases appear here when detected." />
  return <div className="space-y-3 p-4">{queue.data.items.map(c => <Card key={c.case_id}>
    <div className="flex min-w-0 items-start justify-between gap-3">
      <div className="min-w-0"><h2 className="truncate text-base font-semibold text-navy">{c.business_name}</h2><p className="mt-1 break-all text-xs text-muted">{c.case_type} · <span>{c.case_id}</span></p></div>
      {c.disputed_amount_text && <AmountText amount={c.disputed_amount_text} size="large" className="shrink-0" />}
    </div>
    <p className={`mt-3 inline-flex min-h-8 items-center rounded-chip px-3 text-xs font-semibold text-white ${c.weak_evidence_share >= .67 ? 'bg-alert' : c.weak_evidence_share >= .34 ? 'bg-notice' : 'bg-credit'}`}>Weak evidence: {Math.round(c.weak_evidence_share * 100)}%</p>
    {c.escalation_reasons.length > 0 && <p className="mt-2 text-sm text-alert">{c.escalation_reasons.join(', ')}</p>}
    <button className="mt-3 min-h-touch w-full rounded-chip bg-cyan px-4 text-sm font-bold text-navy" onClick={() => navigate('/officer/cases/' + encodeURIComponent(c.case_id))}>Review case</button>
  </Card>)}</div>
}
function Case({ caseId }: { caseId: string }) {
  const client = useQueryClient(), [note, setNote] = useState(''), [officerRef, setOfficerRef] = useState('demo-officer')
  const detail = useQuery({ queryKey: ['officer-case', caseId], queryFn: () => api<OfficerCase>('/app/officer/cases/' + encodeURIComponent(caseId), {}, true), refetchInterval: 2000 })
  const packId = detail.data?.pack_id
  const evidence = useQuery({ queryKey: ['freeze-pack', packId], enabled: Boolean(packId) && detail.data?.case.case_type === 'freeze', queryFn: async () => {
    const pack = await api<FreezePack>('/packs/' + encodeURIComponent(packId!) + '.json', {}, true)
    if (pack.pack_id !== packId || pack.case_id !== caseId || pack.merchant_id !== detail.data?.case.merchant_id) throw new Error('Evidence belongs to a different case or pack')
    return pack
  } })
  const download = useMutation({ mutationFn: () => downloadPack(detail.data!.pdf_url!) })
  const decision = useMutation({ mutationFn: async (action: 'approve' | 'reject') => {
    const data = detail.data
    if (!data?.pack_id || !officerRef.trim()) throw new Error('Pack and officer identity are required')
    if (data.case.case_type === 'freeze' && !evidence.data) throw new Error('Load the freeze evidence before recording a decision')
    if (action === 'reject' && !note.trim()) throw new Error('Enter a reason before rejecting')
    // Read the merchant's current sim clock; never date approval using the browser clock.
    const home = await api<Home>(forMerchant('/app/home').replace(/merchant=[^&]+/, 'merchant=' + encodeURIComponent(data.case.merchant_id)))
    return api<{ status: string }>('/packs/' + encodeURIComponent(data.pack_id) + '/' + action, post({ officer_ref: officerRef.trim(), sim_at: home.as_of,
      ...(action === 'approve' ? { note: note.trim() || null } : { reason: note.trim() }) }), true)
  }, onSuccess: () => { void client.invalidateQueries({ queryKey: ['officer-case', caseId] }); void client.invalidateQueries({ queryKey: ['officer-queue'] }) } })
  if (detail.isPending) return <div className="p-4"><Skeleton className="h-64" /></div>
  if (detail.error) return <Notice error={detail.error} retry={() => void detail.refetch()} />
  const data = detail.data
  const reviewable = data.status === 'awaiting_approval' || data.status === 'pack_built'
  return <>
    <div className="space-y-4 p-4">
      <Card><div className="flex min-w-0 items-start justify-between gap-3"><div className="min-w-0"><h2 className="truncate text-base font-semibold text-navy">{data.case.business_name}</h2><p className="mt-1 break-all text-xs text-muted">{data.case.case_id}</p></div>
        {data.case.disputed_amount_text && <AmountText amount={data.case.disputed_amount_text} size="large" className="shrink-0" />}</div>
        <div className="mt-4 flex flex-wrap items-center gap-2"><p role="status" className="inline-flex min-h-8 items-center rounded-chip bg-cyan-50 px-3 text-sm font-semibold text-navy">{data.status.replaceAll('_', ' ')}</p>
          <p className={`text-sm font-semibold ${data.chain_ok ? 'text-credit' : 'text-alert'}`}>Ledger chain: {data.chain_ok ? 'verified' : 'verification failed'}</p></div>
      </Card>
      {data.case.case_type === 'freeze' && data.pack_id && <>
        {evidence.isPending && <Skeleton className="h-48" />}
        {evidence.error && <Notice error={evidence.error} retry={() => void evidence.refetch()} />}
        {evidence.data && <FreezeEvidence pack={evidence.data} />}
      </>}
      <Card><h2 className="mb-3 text-sm font-semibold">Evidence totals</h2>
        <TierBar ariaLabel="Evidence totals" className="mb-4" segments={data.tier_totals.slice(0, 4).map((t, i) => ({ tier: (i + 1) as 1 | 2 | 3 | 4, label: t.label, value: t.amount }))} />
        <div className="divide-y divide-hairline">{data.tier_totals.map((t, i) => <p key={i} className="flex items-center justify-between gap-3 py-2 text-sm"><span className="min-w-0 text-muted">{t.label}</span><AmountText amount={t.amount_text} className="shrink-0" /></p>)}</div>
        {data.case.case_type === 'freeze' && <p className="mt-2 text-xs text-muted">Tier totals cover the disputed payment only.</p>}
        {data.pdf_url && <button className="mt-3 inline-flex min-h-touch items-center text-sm font-semibold text-navy" disabled={download.isPending} onClick={() => download.mutate()}>{download.isPending ? 'Downloading…' : 'Download evidence PDF →'}</button>}
        {download.error && <p role="alert" className="text-sm text-alert">{download.error.message}</p>}
      </Card>
      <Card><h2 className="mb-3 text-sm font-semibold">Timeline</h2><ol className="space-y-3">{data.timeline.map((t, i) => <li key={i} className="grid grid-cols-[10px_1fr] gap-3 text-sm text-muted"><span aria-hidden="true" className="mt-1.5 h-2.5 w-2.5 rounded-full bg-hairline" /><span className="min-w-0 break-words">{t}</span></li>)}</ol></Card>
      {data.case.escalation_reasons.length > 0 && <Card><p className="text-sm text-alert">{data.case.escalation_reasons.join(', ')}</p></Card>}
      {reviewable && <Card>
        <label className="block text-sm font-semibold">Officer reference<input className="mt-2 min-h-touch w-full rounded-chip border border-hairline px-3" value={officerRef} onChange={e => setOfficerRef(e.target.value)} /></label>
        <label className="mt-3 block text-sm font-semibold">Review note / rejection reason<textarea className="mt-2 w-full rounded-card border border-hairline p-3" rows={3} value={note} onChange={e => setNote(e.target.value)} /></label>
      </Card>}
      {decision.error && <p role="alert" className="text-sm text-alert">{decision.error.message}</p>}
      {decision.isSuccess && <p role="status" className="text-sm text-credit">Decision recorded. Waiting for the case to update.</p>}
      <p className="text-xs text-muted">Delivery is simulated. Approval authorizes the workflow to send this evidence pack.</p>
    </div>
    {reviewable && <StickyCTA label={decision.isPending ? 'Recording decision…' : 'Approve and send (simulated)'} disabled={!data.pack_id || !data.chain_ok || (data.case.case_type === 'freeze' && !evidence.data) || !officerRef.trim() || decision.isPending || decision.isSuccess}
      onClick={() => decision.mutate('approve')} secondaryLabel={decision.isPending ? undefined : 'Reject'} onSecondary={() => { if (!decision.isPending && !decision.isSuccess) decision.mutate('reject') }} />}
  </>
}
function FreezeEvidence({ pack }: { pack: FreezePack }) {
  const { matched, found_by, same_amount_candidates: decoys, bill, device, seven_day_credit_count: count } = pack.isolation
  const when = (ts: string) => new Date(ts).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' }) + ' IST'
  return <>
    <Card padding="none" className="overflow-hidden break-words"><h2 className="px-4 pb-1 pt-4 text-sm font-semibold">Disputed payment</h2>
      {matched ? <>
        <TxnRow name={matched.counterparty_name} time={when(matched.ts)} amount={`Recorded amount: ${matched.amount}`}
          channelIcon={<Clock3 aria-hidden="true" />} channelLabel="Disputed payment" label={`${matched.txn_id} · UTR ${matched.utr}`} tier={1}
          tierLabel={found_by[0] === 'utr' ? 'UTR match' : found_by[0] === 'amount_date' ? 'Amount + date match' : 'Disputed payment'} />
        <div className="px-4 pb-4"><div className="mt-3 flex flex-wrap gap-2">{found_by.map(badge => <span key={badge} className="inline-flex min-h-8 items-center gap-1.5 rounded-chip bg-cyan-50 px-3 py-1.5 text-xs font-semibold text-credit"><CheckCircle2 aria-hidden="true" className="h-4 w-4" />{badge === 'utr' ? 'UTR match' : 'Amount + date match'}</span>)}</div>
        <p className="mt-3 text-sm">1 selected from {count} credits in seven days.</p></div>
      </> : <p className="px-4 pb-4 pt-2 text-sm text-alert">No disputed payment matched. Review the case facts before approving.</p>}
      <h2 className="border-t border-hairline px-4 pb-1 pt-4 text-sm font-semibold">Same-amount payments · not selected</h2>
      {decoys.length ? decoys.map(c => <TxnRow key={c.txn_id} name={c.counterparty_name} time={when(c.ts)} amount={`Recorded amount: ${c.amount}`}
        channelIcon={<Clock3 aria-hidden="true" />} channelLabel="Same-amount payments · not selected" label={`${c.txn_id} · UTR ${c.utr}`} tier={4} tierLabel="Same-amount payments · not selected" />)
        : <p className="px-4 pb-4 pt-2 text-sm text-muted">No other same-amount payments in this window.</p>}
    </Card>
    <Card className="break-words"><h2 className="text-sm font-semibold">Bill and device evidence</h2>
      {bill ? <div className="mt-2 text-sm"><p>Bill {bill.bill_id} · recorded total {bill.total}</p><ul className="mt-2 list-inside list-disc">{bill.line_items.map((item, i) => <li key={i}>{item}</li>)}</ul></div> : <p className="mt-2 text-sm text-muted">No validated bill attached.</p>}
      {device ? <div className="mt-3 text-sm"><p>Terminal {device.terminal_id} · device {device.device_id}</p><p className="text-xs text-muted">Location: {device.geo.lat}, {device.geo.lon}</p></div> : <p className="mt-3 text-sm text-muted">No device evidence attached.</p>}
    </Card>
  </>
}
