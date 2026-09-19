import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Home as HomeIcon, ListChecks, ShieldCheck, ArrowRight } from 'lucide-react'
import { AmountText, AppBar, BottomNav, Card, ChipGroup, EmptyState, HeaderBand, Skeleton, Stepper } from '../components'
import { api, forMerchant, merchant, post, questionTap } from '../api'
import type { Answer, Home, MerchantCase, Questions } from '../api'
import { LANGUAGES, normalizeLanguage, translator } from '../i18n'
import type { Language, Translator } from '../i18n'

export function Notice({ error, retry, t = translator('en-IN') }: { error: Error; retry: () => void; t?: Translator }) {
  return <Card className="m-4" role="alert"><p className="text-sm text-danger">{error.message}</p><button className="mt-2 min-h-touch text-sm font-semibold text-navy" onClick={retry}>{t('action.tryAgain')}</button></Card>
}
// Core sends the chip's English text; the answer value is the stable enum, so the label comes
// from the catalogue and follows the picker. Falls back to core's text if a key is ever missing.
function chipLabel(t: Translator, answer: string, fallback: string): string {
  const key = `confirm.chip.${answer}`
  const label = t(key)
  return label === key ? fallback : label
}
function useHome() {
  return useQuery({ queryKey: ['home', merchant], queryFn: () => api<Home>(forMerchant('/app/home')), refetchInterval: 3000 })
}
export function MerchantScreens({ path, navigate }: { path: string; navigate: (path: string) => void }) {
  const [language, setLanguage] = useState(() => normalizeLanguage(localStorage.getItem('hisaab-language')))
  const confirm = path === '/confirm', cases = path === '/cases'
  const t = translator(language)
  return <main className="mx-auto min-h-dvh max-w-phone bg-bg pb-24">
    <AppBar title={confirm ? t('title.confirm') : cases ? t('title.cases') : t('title.app')}
      onBack={confirm || cases ? () => navigate('/') : undefined} backLabel={t('action.back')}
      trailing={<select aria-label={t('action.language')} className="min-h-touch rounded-chip bg-cyan-50 px-2 text-sm text-navy" value={language} onChange={e => {
        const nextLanguage = normalizeLanguage(e.target.value)
        setLanguage(nextLanguage); localStorage.setItem('hisaab-language', nextLanguage); document.documentElement.lang = nextLanguage
      }}>{LANGUAGES.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select>} />
    {confirm ? <Confirm t={t} language={language} navigate={navigate} /> : cases ? <Cases t={t} /> : <HomeScreen t={t} language={language} navigate={navigate} />}
    <BottomNav ariaLabel={t('nav.aria')} activeId={confirm ? '/confirm' : cases ? '/cases' : '/'} onChange={navigate} items={[
      { id: '/', label: t('nav.home'), icon: <HomeIcon /> },
      { id: '/confirm', label: t('nav.confirm'), icon: <ListChecks /> },
      { id: '/cases', label: t('nav.cases'), icon: <ShieldCheck /> }
    ]} />
  </main>
}
function HomeScreen({ t, language, navigate }: { t: Translator; language: Language; navigate: (path: string) => void }) {
  const home = useHome()
  if (home.isPending) return <div className="p-4"><Skeleton className="h-40" /></div>
  if (home.error) return <Notice error={home.error} retry={() => void home.refetch()} t={t} />
  const data = home.data
  return <>
    <HeaderBand businessName={data.business_name} collectionLabel={t('home.receivedToday')} amount={data.today_received.amount_text}
      paymentSummary={new Date(data.as_of).toLocaleDateString(language, { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Asia/Kolkata' }).replace(/,(\S)/g, ', $1')} />
    <div className="space-y-4 p-4">
      <Card><p className="text-sm text-muted">{t('home.availableBalance')}</p><AmountText amount={data.balance.amount_text} size="large" /></Card>
      <Card>
        <h2 className="text-base font-semibold text-navy">{t('home.toConfirm', { count: data.questions_due })}</h2>
        <p className="mt-1 text-sm text-muted">{t('home.toConfirmHelp')}</p>
        <button onClick={() => navigate('/confirm')} className="mt-4 flex min-h-touch w-full items-center justify-between rounded-chip bg-cyan px-4 text-sm font-bold text-navy">
          {data.questions_due ? t('home.confirmPayments') : t('home.viewConfirmations')}<ArrowRight className="h-4 w-4" />
        </button>
      </Card>
      {data.alerts.map((alert, index) => <Card key={index} className={alert.kind === 'case' ? 'border border-danger' : ''}>
        <h2 className="text-sm font-semibold">{alert.title}</h2><p className="mt-1 text-sm text-muted">{alert.body}</p>
        <button className="mt-2 min-h-touch text-sm font-semibold text-navy" onClick={() => navigate(alert.kind === 'question' ? '/confirm' : '/cases')}>{t('home.viewDetails')}</button>
      </Card>)}
      {data.open_cases > 0 && <button className="min-h-touch w-full rounded-card bg-card p-4 text-left text-sm font-semibold text-navy" onClick={() => navigate('/cases')}>{t('home.openCases', { count: data.open_cases })}</button>}
    </div>
  </>
}
function Confirm({ t, language, navigate }: { t: Translator; language: Language; navigate: (path: string) => void }) {
  const client = useQueryClient(), home = useHome()
  const questions = useQuery({ queryKey: ['questions', merchant], queryFn: () => api<Questions>(forMerchant('/app/questions')), refetchInterval: 2000 })
  const [selected, setSelected] = useState<{ id: string; answer: Answer } | null>(null)
  const [pending, setPending] = useState<{ id: string; since: number } | null>(null)
  const [feedback, setFeedback] = useState('')
  const [timedOut, setTimedOut] = useState(false)
  const send = useMutation({ mutationFn: async () => {
    const question = questions.data?.items[0]
    if (!question || selected?.id !== question.question_id || !home.data) throw new Error(t('confirm.refreshFirst'))
    const result = await api<{ accepted: boolean; forwarded_to_workflow: boolean }>('/assistant/inbound', post(questionTap(question, selected.answer, home.data.as_of)))
    if (!result.accepted || !result.forwarded_to_workflow) throw new Error(t('confirm.workflowUnreachable'))
    return question.question_id
  }, onSuccess: id => { setPending({ id, since: Date.now() }); setTimedOut(false); setFeedback(''); void questions.refetch() } })
  useEffect(() => {
    if (!pending) return
    if (questions.data && !questions.data.items.some(q => q.question_id === pending.id)) {
      setPending(null); setSelected(null); setFeedback(t('confirm.answerSaved'))
      void client.invalidateQueries({ queryKey: ['home', merchant] }); return
    }
    const timeout = setTimeout(() => { setPending(null); setTimedOut(true) }, Math.max(0, 20000 - (Date.now() - pending.since)))
    return () => clearTimeout(timeout)
  }, [pending, questions.data, client, t])
  if (questions.isPending) return <div className="p-4"><Skeleton className="h-64" /></div>
  if (questions.error) return <Notice error={questions.error} retry={() => void questions.refetch()} t={t} />
  const data = questions.data, question = data.items[0]
  if (!question) return <Card className="m-4"><EmptyState icon={<CheckCircle2 />} title={t('confirm.allCaughtUp')} description={data.closing_text} actionLabel={t('confirm.backToHome')} onAction={() => navigate('/')} /><p className="text-center text-sm text-muted">{t('confirm.settledAutomatically', { count: data.automatically_settled_count })}</p></Card>
  return <div className="space-y-4 p-4">
    {feedback && <p role="status" className="text-sm text-credit">{feedback}</p>}
    <p className="text-sm text-muted">{question.position} / {question.total}</p>
    <Card>
      <p className="text-sm font-semibold text-ink">{question.payer_name}</p>
      <p className="mt-1 text-xs text-muted">{new Date(question.ts).toLocaleString(language, { timeZone: 'Asia/Kolkata' })} · {question.channel}</p>
      <div className="mt-4"><AmountText amount={question.amount_text} size="large" /></div>
      <h2 lang={question.language} className="mb-5 mt-3 text-base font-semibold text-navy">{question.question}</h2>
      <ChipGroup label={t('confirm.whatFor')} options={question.answer_chips.map(c => ({ value: c.answer, label: chipLabel(t, c.answer, c.text), disabled: Boolean(pending) || send.isPending }))}
        value={selected?.id === question.question_id ? selected.answer : undefined} onChange={answer => { setSelected({ id: question.question_id, answer }); send.reset(); setTimedOut(false) }} />
      <button disabled={selected?.id !== question.question_id || send.isPending || Boolean(pending) || !home.data}
        onClick={() => send.mutate()} className="mt-5 min-h-touch w-full rounded-chip bg-cyan px-5 text-sm font-bold text-navy disabled:bg-hairline disabled:text-muted">
        {pending || send.isPending ? t('confirm.saving') : t('confirm.saveAnswer')}
      </button>
      {pending && <p role="status" className="mt-3 text-sm text-muted">{t('confirm.received')}</p>}
      {send.error && <p role="alert" className="mt-3 text-sm text-danger">{send.error.message}</p>}
      {home.error && <p role="alert" className="mt-3 text-sm text-danger">{home.error.message}</p>}
      {timedOut && <p role="alert" className="mt-3 text-sm text-danger">{t('confirm.notConfirmed')}</p>}
    </Card>
    <p className="text-xs text-muted">{t('confirm.recordedAlongside')}</p>
  </div>
}
function Cases({ t }: { t: Translator }) {
  const cases = useQuery({ queryKey: ['cases', merchant], queryFn: () => api<{ items: MerchantCase[] }>(forMerchant('/app/cases')), refetchInterval: 3000 })
  if (cases.isPending) return <div className="p-4"><Skeleton className="h-48" /></div>
  if (cases.error) return <Notice error={cases.error} retry={() => void cases.refetch()} t={t} />
  if (!cases.data.items.length) return <EmptyState icon={<ShieldCheck />}
    title={t('cases.none')}
    description={t('cases.noneHelp')} />
  const statusIndex: Record<string, number> = { open: 0, building: 0, pack_built: 1, awaiting_approval: 1, approved: 2, sent: 3 }
  return <div className="space-y-4 p-4">{cases.data.items.map(c => <Card key={c.case_id}>
    <h2 className="text-base font-semibold text-navy">{t(`cases.title.${c.case_type}`)}</h2><p className="mt-1 text-xs text-muted">{c.case_id}</p>
    {c.disputed_amount_text && <div className="mt-3"><AmountText amount={c.disputed_amount_text} /></div>}
    <p role="status" className="my-4 text-sm font-semibold">{t(`cases.status.${c.status}`)}</p>
    {['rejected', 'escalated'].includes(c.status) ? <p className="text-sm text-muted">{t('cases.officerReviewing')}</p> : <Stepper ariaLabel={t('cases.progress')} steps={[
      t('cases.stage.opened'), t('cases.stage.packBuilt'), t('cases.stage.approved'), t('cases.stage.sent')
    ].map((title, i) => ({ id: String(i), title,
      status: i < (statusIndex[c.status] ?? 0) || c.status === 'sent' ? 'complete' : i === (statusIndex[c.status] ?? 0) ? 'current' : 'upcoming' }))} />}
    {c.case_type === 'freeze' && <p className="mt-4 text-xs text-muted">{t('cases.deliverySimulated')}</p>}
  </Card>)}</div>
}
