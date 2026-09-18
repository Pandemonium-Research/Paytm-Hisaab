export interface DisplayAmount { amount: number; amount_text: string }
export interface Home {
  merchant_id: string; business_name: string; as_of: string
  balance: DisplayAmount; today_received: DisplayAmount; questions_due: number; open_cases: number
  alerts: { kind: string; title: string; body: string; href: string }[]
}
export type Answer = 'sale' | 'family' | 'own_money' | 'loan_or_gift' | 'not_sure'
export interface Question {
  question_id: string; txn_id: string; amount_text: string; ts: string; payer_name: string
  channel: string; question: string; language: string; position: number; total: number
  answer_chips: { answer: Answer; text: string }[]
}
export interface Questions { items: Question[]; automatically_settled_count: number; closing_text: string }
export interface MerchantCase {
  case_id: string; case_type: string; status: string; opened_at: string; title: string
  disputed_amount_text: string | null
}
export interface OfficerCaseRow {
  case_id: string; merchant_id: string; business_name: string; case_type: string
  opened_at: string; disputed_amount_text: string | null; weak_evidence_share: number
  escalation_reasons: string[]
}
export interface OfficerCase {
  case: OfficerCaseRow; pack_id: string | null; status: string; timeline: string[]
  tier_totals: (DisplayAmount & { label: string })[]; chain_ok: boolean; pdf_url: string | null
}
interface IsolationPayment {
  txn_id: string; utr: string; amount: number; ts: string; counterparty_name: string
}
export interface FreezePack {
  pack_id: string; case_id: string; merchant_id: string
  isolation: {
    matched: IsolationPayment | null; found_by: ('utr' | 'amount_date')[]
    same_amount_candidates: IsolationPayment[]; seven_day_credit_count: number
    bill: { bill_id: string; line_items: string[]; total: number } | null
    device: { terminal_id: string; device_id: string; geo: { lat: number; lon: number } } | null
  }
}

export const merchant = new URLSearchParams(location.search).get('merchant') || 'MID_DEMO_SAHANA'
const base = import.meta.env.VITE_API_BASE || '/api'
function roleKey(officer: boolean) {
  return officer
    ? sessionStorage.getItem('hisaab-officer-key') || import.meta.env.VITE_OFFICER_KEY || 'dev-officer'
    : import.meta.env.VITE_APP_KEY || 'dev-app'
}
export async function api<T>(path: string, options: RequestInit = {}, officer = false): Promise<T> {
  const response = await fetch(base + path, {
    ...options, cache: 'no-store', headers: { 'Content-Type': 'application/json', 'X-Hisaab-Key': roleKey(officer), ...options.headers }
  })
  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try {
      const body = await response.json()
      detail = typeof body.detail === 'string' ? body.detail : body.detail?.reason || body.error?.message || detail
    } catch { /* Preserve the HTTP error when the proxy returns HTML. */ }
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}
export async function downloadPack(url: string) {
  const target = new URL(url, location.origin)
  if (target.origin !== location.origin || !target.pathname.startsWith('/api/packs/')) throw new Error('Invalid pack download URL')
  const response = await fetch(target, { cache: 'no-store', headers: { 'X-Hisaab-Key': roleKey(true) } })
  if (!response.ok) throw new Error(`Pack download failed (${response.status})`)
  const objectUrl = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = objectUrl; link.download = target.pathname.split('/').pop() || 'evidence.pdf'; link.click()
  setTimeout(() => URL.revokeObjectURL(objectUrl), 30000)
}
export const forMerchant = (path: string) => `${path}?merchant=${encodeURIComponent(merchant)}`
export const post = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })
export function questionTap(question: Question, answer: Answer, simAt: string) {
  return {
    merchant_id: merchant, message_id: crypto.randomUUID(), content_type: 'text',
    text: JSON.stringify({ type: 'question_answer', question_id: question.question_id, txn_id: question.txn_id, answer }),
    language: question.language, sim_at: simAt
  }
}
