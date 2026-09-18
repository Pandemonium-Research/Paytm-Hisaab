import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Home as HomeIcon, ListChecks, ShieldCheck, ArrowRight } from 'lucide-react'
import { AmountText, AppBar, BottomNav, Card, ChipGroup, EmptyState, HeaderBand, Skeleton, Stepper } from '../components'
import { api, forMerchant, merchant, post, questionTap } from '../api'
import type { Answer, Home, MerchantCase, Questions } from '../api'

export function Notice({ error, retry }: { error: Error; retry: () => void }) {
  return <Card className="m-4" role="alert"><p className="text-sm text-danger">{error.message}</p><button className="mt-2 min-h-touch text-sm font-semibold text-navy" onClick={retry}>Try again</button></Card>
}
function useHome() {
  return useQuery({ queryKey: ['home', merchant], queryFn: () => api<Home>(forMerchant('/app/home')), refetchInterval: 3000 })
}
export function MerchantScreens({ path, navigate }: { path: string; navigate: (path: string) => void }) {
  const [language, setLanguage] = useState(localStorage.getItem('hisaab-language') || 'en-IN')
  const confirm = path === '/confirm', cases = path === '/cases'
  const kn = language === 'kn-IN'
  return <main className="mx-auto min-h-dvh max-w-phone bg-bg pb-24">
    <AppBar title={confirm ? (kn ? 'ಪಾವತಿ ದೃಢೀಕರಣ' : 'Confirm payments') : cases ? (kn ? 'ನಿಮ್ಮ ಪ್ರಕರಣಗಳು' : 'Your cases') : 'Paytm Hisaab'}
      onBack={confirm || cases ? () => navigate('/') : undefined} backLabel="Home"
      trailing={<select aria-label="Language" className="min-h-touch rounded-chip bg-cyan-50 px-2 text-sm text-navy" value={language} onChange={e => {
        setLanguage(e.target.value); localStorage.setItem('hisaab-language', e.target.value); document.documentElement.lang = e.target.value
      }}><option value="en-IN">English</option><option value="kn-IN">ಕನ್ನಡ</option></select>} />
    {confirm ? <Confirm kn={kn} navigate={navigate} /> : cases ? <Cases /> : <HomeScreen kn={kn} navigate={navigate} />}
    <BottomNav ariaLabel="Merchant navigation" activeId={confirm ? '/confirm' : cases ? '/cases' : '/'} onChange={navigate} items={[
      { id: '/', label: kn ? 'ಮುಖಪುಟ' : 'Home', icon: <HomeIcon /> },
      { id: '/confirm', label: kn ? 'ದೃಢೀಕರಿಸಿ' : 'Confirm', icon: <ListChecks /> },
      { id: '/cases', label: kn ? 'ಪ್ರಕರಣಗಳು' : 'Cases', icon: <ShieldCheck /> }
    ]} />
  </main>
}
function HomeScreen({ kn, navigate }: { kn: boolean; navigate: (path: string) => void }) {
  const home = useHome()
  if (home.isPending) return <div className="p-4"><Skeleton className="h-40" /></div>
  if (home.error) return <Notice error={home.error} retry={() => void home.refetch()} />
  const data = home.data
  return <>
    <HeaderBand businessName={data.business_name} collectionLabel={kn ? 'ಇಂದಿನ ಸ್ವೀಕೃತಿ' : 'Received today'} amount={data.today_received.amount_text}
      paymentSummary={new Date(data.as_of).toLocaleDateString(kn ? 'kn-IN' : 'en-IN', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Asia/Kolkata' })} />
    <div className="space-y-4 p-4">
      <Card><p className="text-sm text-muted">{kn ? 'ಬಳಸಬಹುದಾದ ಶಿಲ್ಕು' : 'Available balance'}</p><AmountText amount={data.balance.amount_text} size="large" /></Card>
      <Card>
        <h2 className="text-base font-semibold text-navy">{kn ? 'ಪಾವತಿ ದೃಢೀಕರಣ' : `${data.questions_due} payments to confirm`}</h2>
        <p className="mt-1 text-sm text-muted">{kn ? `${data.questions_due} ಪಾವತಿಗಳಿಗೆ ನಿಮ್ಮ ಉತ್ತರ ಬೇಕು.` : 'Help us record what these payments were for.'}</p>
        <button onClick={() => navigate('/confirm')} className="mt-4 flex min-h-touch w-full items-center justify-between rounded-chip bg-cyan px-4 text-sm font-bold text-navy">
          {kn ? 'ಪಾವತಿಗಳನ್ನು ನೋಡಿ' : data.questions_due ? 'Confirm payments' : 'View confirmations'}<ArrowRight className="h-4 w-4" />
        </button>
      </Card>
      {data.alerts.map((alert, index) => <Card key={index} className={alert.kind === 'case' ? 'border border-danger' : ''}>
        <h2 className="text-sm font-semibold">{alert.title}</h2><p className="mt-1 text-sm text-muted">{alert.body}</p>
        <button className="mt-2 min-h-touch text-sm font-semibold text-navy" onClick={() => navigate(alert.kind === 'question' ? '/confirm' : '/cases')}>{kn ? 'ನೋಡಿ' : 'View details'}</button>
      </Card>)}
      {data.open_cases > 0 && <button className="min-h-touch w-full rounded-card bg-card p-4 text-left text-sm font-semibold text-navy" onClick={() => navigate('/cases')}>{data.open_cases} open cases →</button>}
    </div>
  </>
}
function Confirm({ kn, navigate }: { kn: boolean; navigate: (path: string) => void }) {
  const client = useQueryClient(), home = useHome()
  const questions = useQuery({ queryKey: ['questions', merchant], queryFn: () => api<Questions>(forMerchant('/app/questions')), refetchInterval: 2000 })
  const [selected, setSelected] = useState<{ id: string; answer: Answer } | null>(null)
  const [pending, setPending] = useState<{ id: string; since: number } | null>(null)
  const [feedback, setFeedback] = useState('')
  const [timedOut, setTimedOut] = useState(false)
  const send = useMutation({ mutationFn: async () => {
    const question = questions.data?.items[0]
    if (!question || selected?.id !== question.question_id || !home.data) throw new Error('Refresh the question before answering')
    const result = await api<{ accepted: boolean; forwarded_to_workflow: boolean }>('/assistant/inbound', post(questionTap(question, selected.answer, home.data.as_of)))
    if (!result.accepted || !result.forwarded_to_workflow) throw new Error('Your answer could not reach the workflow. Please retry.')
    return question.question_id
  }, onSuccess: id => { setPending({ id, since: Date.now() }); setTimedOut(false); setFeedback(''); void questions.refetch() } })
  useEffect(() => {
    if (!pending) return
    if (questions.data && !questions.data.items.some(q => q.question_id === pending.id)) {
      setPending(null); setSelected(null); setFeedback(kn ? 'ನಿಮ್ಮ ಉತ್ತರ ದಾಖಲಾಗಿದೆ.' : 'Your answer has been saved.')
      void client.invalidateQueries({ queryKey: ['home', merchant] }); return
    }
    const timeout = setTimeout(() => { setPending(null); setTimedOut(true) }, Math.max(0, 20000 - (Date.now() - pending.since)))
    return () => clearTimeout(timeout)
  }, [pending, questions.data, client, kn])
  if (questions.isPending) return <div className="p-4"><Skeleton className="h-64" /></div>
  if (questions.error) return <Notice error={questions.error} retry={() => void questions.refetch()} />
  const data = questions.data, question = data.items[0]
  if (!question) return <Card className="m-4"><EmptyState icon={<CheckCircle2 />} title={kn ? 'ಇಂದಿಗೆ ಮುಗಿದಿದೆ' : 'All caught up'} description={data.closing_text} actionLabel={kn ? 'ಮುಖಪುಟ' : 'Back to home'} onAction={() => navigate('/')} /><p className="text-center text-sm text-muted">{data.automatically_settled_count} payments settled automatically</p></Card>
  return <div className="space-y-4 p-4">
    {feedback && <p role="status" className="text-sm text-credit">{feedback}</p>}
    <p className="text-sm text-muted">{question.position} / {question.total}</p>
    <Card>
      <p className="text-sm font-semibold text-ink">{question.payer_name}</p>
      <p className="mt-1 text-xs text-muted">{new Date(question.ts).toLocaleString(kn ? 'kn-IN' : 'en-IN', { timeZone: 'Asia/Kolkata' })} · {question.channel}</p>
      <div className="mt-4"><AmountText amount={question.amount_text} size="large" /></div>
      <h2 lang={question.language} className="mb-5 mt-3 text-base font-semibold text-navy">{question.question}</h2>
      <ChipGroup label="What was this payment for?" options={question.answer_chips.map(c => ({ value: c.answer, label: c.text, disabled: Boolean(pending) || send.isPending }))}
        value={selected?.id === question.question_id ? selected.answer : undefined} onChange={answer => { setSelected({ id: question.question_id, answer }); send.reset(); setTimedOut(false) }} />
      <button disabled={selected?.id !== question.question_id || send.isPending || Boolean(pending) || !home.data}
        onClick={() => send.mutate()} className="mt-5 min-h-touch w-full rounded-chip bg-cyan px-5 text-sm font-bold text-navy disabled:bg-hairline disabled:text-muted">
        {pending || send.isPending ? (kn ? 'ದಾಖಲಾಗುತ್ತಿದೆ…' : 'Saving answer…') : (kn ? 'ಉತ್ತರ ಉಳಿಸಿ' : 'Save answer')}
      </button>
      {pending && <p role="status" className="mt-3 text-sm text-muted">{kn ? 'ಉತ್ತರ ಸ್ವೀಕರಿಸಲಾಗಿದೆ. ದೃಢೀಕರಣಕ್ಕಾಗಿ ಕಾಯಿರಿ.' : 'Answer received. Waiting for confirmation.'}</p>}
      {send.error && <p role="alert" className="mt-3 text-sm text-danger">{send.error.message}</p>}
      {home.error && <p role="alert" className="mt-3 text-sm text-danger">{home.error.message}</p>}
      {timedOut && <p role="alert" className="mt-3 text-sm text-danger">We could not confirm that your answer was saved. Refresh before retrying.</p>}
    </Card>
    <p className="text-xs text-muted">{kn ? 'ನಿಮ್ಮ ಉತ್ತರ ಪ್ರತ್ಯೇಕವಾಗಿ ದಾಖಲಾಗುತ್ತದೆ.' : 'Your answer is recorded alongside the automatic classification.'}</p>
  </div>
}
function Cases() {
  const cases = useQuery({ queryKey: ['cases', merchant], queryFn: () => api<{ items: MerchantCase[] }>(forMerchant('/app/cases')), refetchInterval: 3000 })
  if (cases.isPending) return <div className="p-4"><Skeleton className="h-48" /></div>
  if (cases.error) return <Notice error={cases.error} retry={() => void cases.refetch()} />
  if (!cases.data.items.length) return <EmptyState icon={<ShieldCheck />} title="No open cases" description="Case updates will appear here." />
  const stages = ['Case opened', 'Evidence pack built', 'Officer approved', 'Sent to bank and police (simulated)']
  const statusIndex: Record<string, number> = { open: 0, building: 0, pack_built: 1, awaiting_approval: 1, approved: 2, sent: 3 }
  return <div className="space-y-4 p-4">{cases.data.items.map(c => <Card key={c.case_id}>
    <h2 className="text-base font-semibold text-navy">{c.title}</h2><p className="mt-1 text-xs text-muted">{c.case_id}</p>
    {c.disputed_amount_text && <div className="mt-3"><AmountText amount={c.disputed_amount_text} /></div>}
    <p role="status" className="my-4 text-sm font-semibold">{c.status.replaceAll('_', ' ')}</p>
    {['rejected', 'escalated'].includes(c.status) ? <p className="text-sm text-muted">An officer is reviewing the next steps.</p> : <Stepper ariaLabel="Case progress" steps={stages.map((title, i) => ({ id: String(i), title,
      status: i < (statusIndex[c.status] ?? 0) || c.status === 'sent' ? 'complete' : i === (statusIndex[c.status] ?? 0) ? 'current' : 'upcoming' }))} />}
    {c.case_type === 'freeze' && <p className="mt-4 text-xs text-muted">Evidence delivery is simulated. The bank decides whether to change the hold.</p>}
  </Card>)}</div>
}
