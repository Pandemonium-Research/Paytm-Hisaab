import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ShieldCheck } from 'lucide-react'
import { AmountText, AppBar, Card, EmptyState, Skeleton, StickyCTA } from '../components'
import { api, downloadPack, forMerchant, post } from '../api'
import type { Home, OfficerCase, OfficerCaseRow } from '../api'
import { Notice } from './Merchant'

export function OfficerScreens({ path, navigate }: { path: string; navigate: (path: string) => void }) {
  const caseId = path.startsWith('/officer/cases/') ? decodeURIComponent(path.slice('/officer/cases/'.length)) : null
  return <main className="mx-auto min-h-dvh max-w-phone bg-bg pb-32">
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
    <h2 className="text-base font-semibold text-navy">{c.business_name}</h2><p className="mt-1 text-sm text-muted">{c.case_type} · {c.case_id}</p>
    {c.disputed_amount_text && <div className="mt-3"><AmountText amount={c.disputed_amount_text} /></div>}
    <p className="mt-2 text-xs text-muted">Weak evidence: {Math.round(c.weak_evidence_share * 100)}%</p>
    {c.escalation_reasons.length > 0 && <p className="mt-2 text-sm text-danger">{c.escalation_reasons.join(', ')}</p>}
    <button className="mt-3 min-h-touch w-full rounded-chip bg-cyan px-4 text-sm font-bold text-navy" onClick={() => navigate('/officer/cases/' + encodeURIComponent(c.case_id))}>Review case</button>
  </Card>)}</div>
}
function Case({ caseId }: { caseId: string }) {
  const client = useQueryClient(), [note, setNote] = useState(''), [officerRef, setOfficerRef] = useState('demo-officer')
  const detail = useQuery({ queryKey: ['officer-case', caseId], queryFn: () => api<OfficerCase>('/app/officer/cases/' + encodeURIComponent(caseId), {}, true), refetchInterval: 2000 })
  const download = useMutation({ mutationFn: () => downloadPack(detail.data!.pdf_url!) })
  const decision = useMutation({ mutationFn: async (action: 'approve' | 'reject') => {
    const data = detail.data
    if (!data?.pack_id || !officerRef.trim()) throw new Error('Pack and officer identity are required')
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
      <Card><h2 className="text-base font-semibold text-navy">{data.case.business_name}</h2><p className="mt-1 text-xs text-muted">{data.case.case_id}</p>
        {data.case.disputed_amount_text && <div className="mt-3"><AmountText amount={data.case.disputed_amount_text} size="large" /></div>}
        <p role="status" className="mt-3 text-sm font-semibold">{data.status.replaceAll('_', ' ')}</p>
        <p className="mt-2 text-sm">Ledger chain: {data.chain_ok ? 'verified' : 'verification failed'}</p>
      </Card>
      <Card><h2 className="mb-3 text-sm font-semibold">Evidence totals</h2>{data.tier_totals.map((t, i) => <p key={i} className="flex justify-between py-2 text-sm"><span>{t.label}</span><AmountText amount={t.amount_text} /></p>)}
        {data.pdf_url && <button className="mt-3 inline-flex min-h-touch items-center text-sm font-semibold text-navy" disabled={download.isPending} onClick={() => download.mutate()}>{download.isPending ? 'Downloading…' : 'Download evidence PDF →'}</button>}
        {download.error && <p role="alert" className="text-sm text-danger">{download.error.message}</p>}
      </Card>
      <Card><h2 className="mb-2 text-sm font-semibold">Timeline</h2><ol className="space-y-2">{data.timeline.map((t, i) => <li key={i} className="text-sm text-muted">{t}</li>)}</ol></Card>
      {data.case.escalation_reasons.length > 0 && <Card><p className="text-sm text-danger">{data.case.escalation_reasons.join(', ')}</p></Card>}
      {reviewable && <Card>
        <label className="block text-sm font-semibold">Officer reference<input className="mt-2 min-h-touch w-full rounded-chip border border-hairline px-3" value={officerRef} onChange={e => setOfficerRef(e.target.value)} /></label>
        <label className="mt-3 block text-sm font-semibold">Review note / rejection reason<textarea className="mt-2 w-full rounded-card border border-hairline p-3" rows={3} value={note} onChange={e => setNote(e.target.value)} /></label>
      </Card>}
      {decision.error && <p role="alert" className="text-sm text-danger">{decision.error.message}</p>}
      {decision.isSuccess && <p role="status" className="text-sm text-credit">Decision recorded. Waiting for the case to update.</p>}
      <p className="text-xs text-muted">Delivery is simulated. Approval authorizes the workflow to send this evidence pack.</p>
    </div>
    {reviewable && <StickyCTA label={decision.isPending ? 'Recording decision…' : 'Approve and send (simulated)'} disabled={!data.pack_id || !data.chain_ok || !officerRef.trim() || decision.isPending || decision.isSuccess}
      onClick={() => decision.mutate('approve')} secondaryLabel={decision.isPending ? undefined : 'Reject'} onSecondary={() => { if (!decision.isPending && !decision.isSuccess) decision.mutate('reject') }} />}
  </>
}
