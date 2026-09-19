import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, BarChart3, CheckCircle2, ChevronRight, Clock3, FileWarning, Home as HomeIcon, ListChecks, MessageCircle, ShieldCheck, Sparkles } from 'lucide-react'
import { AmountText, AppBar, BottomNav, Card, ChipGroup, EmptyState, Skeleton, Stepper, ThresholdProgress, TxnRow, type TxnLabelTone } from '../components'
import { api, forMerchant, merchant, post, questionTap } from '../api'
import type { Answer, Home, MerchantCase, PaymentLabel, Payments, Questions, Turnover } from '../api'
import { LANGUAGES, normalizeLanguage, translator } from '../i18n'
import type { Language, Translator } from '../i18n'
import { ChatScreen } from './Chat'

export function Notice({ error, retry, t = translator('en-IN') }: { error: Error; retry: () => void; t?: Translator }) {
  return <Card className="m-4" role="alert"><p className="text-sm text-alert">{error.message}</p><button className="mt-2 min-h-touch text-sm font-semibold text-navy" onClick={retry}>{t('action.tryAgain')}</button></Card>
}
// Core sends the chip's English text; the answer value is the stable enum, so the label comes
// from the catalogue and follows the picker. Falls back to core's text if a key is ever missing.
function chipLabel(t: Translator, answer: string, fallback: string): string {
  const key = `confirm.chip.${answer}`
  const label = t(key)
  return label === key ? fallback : label
}
function useHome(enabled = true) {
  return useQuery({ queryKey: ['home', merchant], queryFn: () => api<Home>(forMerchant('/app/home')), refetchInterval: 3000, enabled })
}
function useTurnover() {
  return useQuery({ queryKey: ['turnover', merchant], queryFn: () => api<Turnover>(forMerchant('/app/turnover')), retry: false })
}
function useQuestionsSummary() {
  return useQuery({ queryKey: ['questions', merchant], queryFn: () => api<Questions>(forMerchant('/app/questions')), retry: false })
}
function useRecentPayments() {
  return useQuery({ queryKey: ['payments', merchant, 4], queryFn: () => api<Payments>(`${forMerchant('/app/payments')}&limit=4`), retry: false })
}
export function MerchantScreens({ path, navigate }: { path: string; navigate: (path: string) => void }) {
  const [language, setLanguage] = useState(() => normalizeLanguage(localStorage.getItem('hisaab-language')))
  const confirm = path === '/confirm', cases = path === '/cases', chat = path === '/chat'
  const home = useHome(!confirm && !cases && !chat)
  const t = translator(language)
  return <main className="mx-auto min-h-dvh max-w-phone overflow-x-hidden bg-bg pb-28">
    <AppBar title={confirm ? t('title.confirm') : cases ? t('title.cases') : chat ? t('title.chat') : t('title.app')}
      onBack={confirm || cases || chat ? () => navigate('/') : undefined} backLabel={t('action.back')}
      merchantName={!confirm && !cases && !chat ? home.data?.business_name : undefined} tagline={!confirm && !cases && !chat ? t('home.tagline') : undefined}
      trailing={<select aria-label={t('action.language')} className="min-h-touch max-w-[112px] rounded-chip bg-cyan-50 px-2 text-sm text-navy" value={language} onChange={e => {
        const nextLanguage = normalizeLanguage(e.target.value)
        setLanguage(nextLanguage); localStorage.setItem('hisaab-language', nextLanguage); document.documentElement.lang = nextLanguage
      }}>{LANGUAGES.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select>} />
    {confirm ? <Confirm t={t} language={language} navigate={navigate} /> : cases ? <Cases t={t} /> : chat ? <ChatScreen t={t} language={language} formatTime={displayTime} /> : <HomeScreen home={home} t={t} language={language} navigate={navigate} />}
    <BottomNav ariaLabel={t('nav.aria')} activeId={confirm ? '/confirm' : cases ? '/cases' : '/'} onChange={navigate} items={[
      { id: '/', label: t('nav.home'), icon: <HomeIcon /> },
      { id: '/confirm', label: t('nav.confirm'), icon: <ListChecks /> },
      { id: '/cases', label: t('nav.cases'), icon: <ShieldCheck /> }
    ]} />
  </main>
}

function greetingKey(asOf: string): string {
  const hourPart = new Intl.DateTimeFormat('en-US', { hour: 'numeric', hourCycle: 'h23', timeZone: 'Asia/Kolkata' })
    .formatToParts(new Date(asOf)).find(part => part.type === 'hour')?.value
  const hour = Number(hourPart ?? 0)
  return hour < 12 ? 'home.greetingMorning' : hour < 17 ? 'home.greetingAfternoon' : 'home.greetingEvening'
}

function firstName(businessName: string): string {
  return businessName.trim().split(/\s+/)[0]
}

function displayDate(value: string, language: Language): string {
  return new Intl.DateTimeFormat(language, { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Asia/Kolkata' }).format(new Date(value))
}

export function displayTime(value: string, language: Language): string {
  return new Intl.DateTimeFormat(language, { hour: 'numeric', minute: '2-digit', timeZone: 'Asia/Kolkata' }).format(new Date(value))
}

function labelPresentation(t: Translator, label: PaymentLabel | null): { label: string; tone: TxnLabelTone } {
  if (!label || label === 'unclassified') return { label: t('home.label.underReview'), tone: 'review' }
  const tones: Record<Exclude<PaymentLabel, 'unclassified'>, TxnLabelTone> = {
    taxable_supply: 'credit', exempt_supply: 'cyan', personal_transfer: 'personal', inter_account: 'cyan-soft',
    duplicate: 'notice', refund_reversal: 'notice', non_business: 'muted'
  }
  return { label: t(`home.label.${label}`), tone: tones[label] }
}

function HomeScreen({ home, t, language, navigate }: { home: ReturnType<typeof useHome>; t: Translator; language: Language; navigate: (path: string) => void }) {
  const turnover = useTurnover()
  const questions = useQuestionsSummary()
  const payments = useRecentPayments()
  if (home.isPending) return <div className="p-4"><Skeleton className="h-40" /></div>
  if (home.error) return <Notice error={home.error} retry={() => void home.refetch()} t={t} />
  const data = home.data
  const summary = questions.data ? {
    settled: questions.data.automatically_settled_count,
    total: questions.data.automatically_settled_count + data.questions_due
  } : null
  const turnoverPercent = turnover.data && turnover.data.threshold > 0 ? Math.round(turnover.data.aggregate / turnover.data.threshold * 100) : null
  return <div className="space-y-4 p-4">
      <section className="overflow-hidden rounded-card bg-cyan-50 p-4 text-navy shadow-card">
        <h2 className="text-lg font-bold">{t(greetingKey(data.as_of), { name: firstName(data.business_name) })}</h2>
        <p className="mt-1 text-sm leading-5 text-navy">{t('home.greetingHelp')}</p>
        {summary && <div className={`mt-4 grid ${summary.total > 0 ? 'grid-cols-3' : 'grid-cols-2'} gap-2 border-t border-cyan pt-4`}>
          <div className="min-w-0 text-center">
            <span className="mx-auto flex h-10 w-10 items-center justify-center rounded-card bg-credit/10 text-credit"><CheckCircle2 aria-hidden="true" className="h-5 w-5" /></span>
            <p className="amount-numerals mt-2 text-base font-bold text-navy">{summary.total}</p>
            <p className="mt-0.5 break-words text-xs leading-4 text-muted">{t('home.transactionsClassified')}</p>
          </div>
          {summary.total > 0 && <div className="min-w-0 text-center">
            <span className="mx-auto flex h-10 w-10 items-center justify-center rounded-card bg-cyan text-navy"><Sparkles aria-hidden="true" className="h-5 w-5" /></span>
            <p className="amount-numerals mt-2 text-base font-bold text-navy">{Math.round(summary.settled / summary.total * 100)}%</p>
            <p className="mt-0.5 break-words text-xs leading-4 text-muted">{t('home.autoClassified')}</p>
          </div>}
          <div className="min-w-0 text-center">
            <span className="mx-auto flex h-10 w-10 items-center justify-center rounded-card bg-personal/10 text-personal"><Clock3 aria-hidden="true" className="h-5 w-5" /></span>
            <p className="amount-numerals mt-2 text-base font-bold text-navy">{data.questions_due}</p>
            <p className="mt-0.5 break-words text-xs leading-4 text-muted">{t('home.awaitingConfirmation')}</p>
          </div>
        </div>}
      </section>
      {turnover.data && <Card>
        <div className="mb-4 flex items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-card bg-cyan-50 text-cyan"><BarChart3 aria-hidden="true" className="h-6 w-6" /></span>
          <h2 className="text-base font-semibold text-navy">{t('home.turnover')}</h2>
        </div>
        <ThresholdProgress current={turnover.data.aggregate} threshold={turnover.data.threshold} maximum={turnover.data.threshold}
          currentLabel={turnover.data.aggregate_text} thresholdLabel={turnover.data.threshold_text} showThresholdMarker={false} fillTone="credit"
          detailLabel={turnoverPercent === null ? undefined : t('home.thresholdPercent', { percent: turnoverPercent, threshold: turnover.data.threshold_text })} />
        <p className="mt-3 text-xs text-muted">{turnover.data.period}</p>
        {turnover.data.registration_required && <p className="mt-3 font-semibold text-alert">{t('home.registrationRequired')}</p>}
        {turnover.data.crossed_on && <p className="mt-1 text-sm text-alert">{t('home.thresholdCrossed', { date: displayDate(turnover.data.crossed_on, language) })}</p>}
        {!turnover.data.registration_required && turnover.data.projected_crossing_on && <p className="mt-3 text-sm font-medium text-credit">{t('home.projectedCrossing', { date: displayDate(turnover.data.projected_crossing_on, language) })}</p>}
      </Card>}
      <Card className="border border-hairline shadow-none">
        <h2 className="text-base font-semibold text-navy">{t('home.toConfirm', { count: data.questions_due })}</h2>
        <p className="mt-1 text-sm text-muted">{t('home.toConfirmHelp')}</p>
        <button onClick={() => navigate('/confirm')} className="mt-4 flex min-h-touch w-full items-center justify-between rounded-card bg-cyan px-4 text-sm font-bold text-navy">
          {data.questions_due ? t('home.confirmPayments') : t('home.viewConfirmations')}<ArrowRight className="h-4 w-4" />
        </button>
      </Card>
      {/* The question alert says what the card above already says, so only case alerts are shown. */}
      {data.alerts.filter(alert => alert.kind !== 'question').map((alert, index) => alert.kind === 'case' ? <Card key={index} className="border border-alert bg-alert/10 shadow-none">
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-card bg-alert text-card"><FileWarning aria-hidden="true" className="h-6 w-6" /></span>
          <div className="min-w-0 flex-1"><h2 className="text-sm font-semibold text-alert">{alert.title}</h2><p className="mt-1 text-sm text-muted">{alert.body}</p></div>
          <button className="flex min-h-touch min-w-touch shrink-0 items-center justify-center rounded-chip text-alert" onClick={() => navigate('/cases')}><span className="sr-only">{t('home.viewDetails')}</span><ChevronRight aria-hidden="true" className="h-5 w-5" /></button>
        </div>
      </Card> : <Card key={index} className="border border-hairline shadow-none">
        <h2 className="text-sm font-semibold text-ink">{alert.title}</h2><p className="mt-1 text-sm text-muted">{alert.body}</p>
        <button className="mt-2 inline-flex min-h-touch items-center gap-1 text-sm font-semibold text-navy" onClick={() => navigate(alert.kind === 'question' ? '/confirm' : '/cases')}>{t('home.viewDetails')}<ChevronRight aria-hidden="true" className="h-4 w-4" /></button>
      </Card>)}
      {data.open_cases > 0 && <button className="min-h-touch w-full rounded-card bg-card p-4 text-left text-sm font-semibold text-navy" onClick={() => navigate('/cases')}>{t('home.openCases', { count: data.open_cases })}</button>}
      {payments.data && payments.data.items.length > 0 && <Card padding="none" className="overflow-hidden">
        <div className="flex items-center gap-3 border-b border-hairline px-4 py-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-card bg-cyan-50 text-cyan"><ListChecks aria-hidden="true" className="h-5 w-5" /></span>
          <h2 className="text-base font-semibold text-navy">{t('home.recentTransactions')}</h2>
        </div>
        {payments.data.items.map(payment => {
          const presentation = labelPresentation(t, payment.effective_label)
          return <TxnRow key={payment.txn_id} name={payment.counterparty_name} date={displayDate(payment.ts, language)} time={displayTime(payment.ts, language)}
            amount={payment.amount_text} label={presentation.label} labelTone={presentation.tone} />
        })}
      </Card>}
      <button type="button" onClick={() => navigate('/chat')} className="flex min-h-[76px] w-full items-center gap-3 rounded-card bg-cyan-50 px-4 py-3 text-left shadow-card">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-card text-navy"><MessageCircle aria-hidden="true" className="h-6 w-6" /></span>
        <span className="min-w-0 flex-1"><span className="block text-base font-bold text-navy">{t('home.askHisaab')}</span><span className="mt-0.5 block text-sm text-muted">{t('home.askHisaabHelp')}</span></span>
        <ChevronRight aria-hidden="true" className="h-6 w-6 shrink-0 text-cyan" />
      </button>
    </div>
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
    <div className="flex min-w-0 items-center justify-between gap-4">
      <p className="shrink-0 text-sm font-medium text-muted">{question.position} / {question.total}</p>
      <div aria-hidden="true" className="flex min-w-0 flex-1 justify-end gap-1.5 overflow-hidden">{Array.from({ length: question.total }, (_, index) => <span key={index} className={`h-2.5 w-2.5 shrink-0 rounded-full ${index + 1 <= question.position ? 'bg-cyan' : 'bg-hairline'}`} />)}</div>
    </div>
    <Card>
      <div className="flex min-w-0 items-start justify-between gap-3">
        <p className="min-w-0 break-words text-base font-bold text-navy">{question.payer_name}</p>
        <AmountText amount={question.amount_text} size="large" className="shrink-0" />
      </div>
      <p className="mt-1 text-xs text-muted">{new Date(question.ts).toLocaleString(language, { timeZone: 'Asia/Kolkata' })} · {question.channel}</p>
      <h2 lang={question.language} className="mb-5 mt-5 text-base font-semibold text-ink">{question.question}</h2>
      <ChipGroup label={t('confirm.whatFor')} options={question.answer_chips.map(c => ({ value: c.answer, label: chipLabel(t, c.answer, c.text), disabled: Boolean(pending) || send.isPending }))}
        value={selected?.id === question.question_id ? selected.answer : undefined} onChange={answer => { setSelected({ id: question.question_id, answer }); send.reset(); setTimedOut(false) }} />
      <button disabled={selected?.id !== question.question_id || send.isPending || Boolean(pending) || !home.data}
        onClick={() => send.mutate()} className="mt-5 min-h-touch w-full rounded-chip bg-cyan px-5 text-sm font-bold text-navy disabled:bg-hairline disabled:text-muted">
        {pending || send.isPending ? t('confirm.saving') : t('confirm.saveAnswer')}
      </button>
      {pending && <p role="status" className="mt-3 text-sm text-muted">{t('confirm.received')}</p>}
      {send.error && <p role="alert" className="mt-3 text-sm text-alert">{send.error.message}</p>}
      {home.error && <p role="alert" className="mt-3 text-sm text-alert">{home.error.message}</p>}
      {timedOut && <p role="alert" className="mt-3 text-sm text-alert">{t('confirm.notConfirmed')}</p>}
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
    <div className="flex min-w-0 items-start justify-between gap-3">
      <div className="min-w-0"><h2 className="text-base font-semibold text-navy">{t(`cases.title.${c.case_type}`)}</h2><p className="mt-1 break-all text-xs text-muted">{c.case_id}</p></div>
      {c.disputed_amount_text && <AmountText amount={c.disputed_amount_text} className="shrink-0" />}
    </div>
    <p role="status" className="mb-5 mt-4 inline-flex min-h-8 items-center rounded-chip bg-cyan-50 px-3 text-sm font-semibold text-navy">{t(`cases.status.${c.status}`)}</p>
    {['rejected', 'escalated'].includes(c.status) ? <p className="text-sm text-muted">{t('cases.officerReviewing')}</p> : <Stepper ariaLabel={t('cases.progress')} steps={[
      t('cases.stage.opened'), t('cases.stage.packBuilt'), t('cases.stage.approved'), t('cases.stage.sent')
    ].map((title, i) => ({ id: String(i), title,
      status: i < (statusIndex[c.status] ?? 0) || c.status === 'sent' ? 'complete' : i === (statusIndex[c.status] ?? 0) ? 'current' : 'upcoming' }))} />}
    {c.case_type === 'freeze' && <p className="mt-2 border-t border-hairline pt-3 text-xs leading-5 text-muted">{t('cases.deliverySimulated')}</p>}
  </Card>)}</div>
}
