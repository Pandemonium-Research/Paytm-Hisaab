import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MessageCircle, Send } from 'lucide-react'
import { Card, EmptyState, Skeleton } from '../components'
import { api, forMerchant, merchant, post, type Home } from '../api'
import type { Conversation } from '../api'
import type { Language, Translator } from '../i18n'

function newMessageId(): string {
  return `MSG-${crypto.randomUUID().replace(/-/g, '')}`
}

// The Confirm screen posts its answers down the same pipe, as a JSON envelope the workflow
// parses. That is machine traffic, not conversation, so it is kept out of the thread rather
// than shown to the merchant as a wall of braces.
function isMachineEnvelope(text: string): boolean {
  const trimmed = text.trim()
  if (!trimmed.startsWith('{')) return false
  try { return typeof (JSON.parse(trimmed) as { type?: unknown }).type === 'string' } catch { return false }
}

function hasReplyAfter(items: Conversation['items'], inMessageId: string): boolean {
  const index = items.findIndex(item => item.message_id === inMessageId)
  if (index < 0) return false
  return items.slice(index + 1).some(item => item.direction === 'out')
}

export function ChatScreen({ t, language, formatTime }: { t: Translator; language: Language; formatTime: (value: string, language: Language) => string }) {
  const client = useQueryClient()
  const scrollRef = useRef<HTMLDivElement>(null)
  const [draft, setDraft] = useState('')
  const [awaitingInId, setAwaitingInId] = useState<string | null>(null)
  const [failedText, setFailedText] = useState<string | null>(null)

  const home = useQuery({ queryKey: ['home', merchant], queryFn: () => api<Home>(forMerchant('/app/home')) })
  const conversation = useQuery({
    queryKey: ['conversation', merchant],
    queryFn: () => api<Conversation>(forMerchant('/app/conversation')),
    refetchInterval: 2000
  })

  const items = (conversation.data?.items ?? []).filter(item => !isMachineEnvelope(item.text))

  useEffect(() => {
    if (awaitingInId && hasReplyAfter(items, awaitingInId)) setAwaitingInId(null)
  }, [items, awaitingInId])

  useEffect(() => {
    const node = scrollRef.current
    if (!node) return
    node.scrollTop = node.scrollHeight
  }, [items.length, awaitingInId])

  const send = useMutation({
    mutationFn: async (text: string) => {
      if (!home.data) throw new Error(t('chat.failed'))
      const message_id = newMessageId()
      const body = {
        merchant_id: merchant,
        message_id,
        content_type: 'text',
        text,
        language,
        sim_at: home.data.as_of
      }
      const result = await api<{ accepted: boolean }>('/assistant/inbound', post(body))
      if (!result.accepted) throw new Error(t('chat.failed'))
      return message_id
    },
    onSuccess: messageId => {
      setFailedText(null)
      setAwaitingInId(messageId)
      void client.invalidateQueries({ queryKey: ['conversation', merchant] })
    },
    onError: (_error, text) => setFailedText(text)
  })

  const submit = (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || send.isPending || !home.data) return
    setDraft('')
    send.mutate(trimmed)
  }

  const thinking = Boolean(awaitingInId && !hasReplyAfter(items, awaitingInId))

  if (conversation.isPending) return <div className="p-4"><Skeleton className="h-48" /></div>
  if (conversation.error) return <Card className="m-4" role="alert"><p className="text-sm text-alert">{conversation.error.message}</p><button className="mt-2 min-h-touch text-sm font-semibold text-navy" onClick={() => void conversation.refetch()}>{t('action.tryAgain')}</button></Card>

  return (
    <div className="flex min-h-[calc(100dvh-72px)] flex-col">
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 pb-36 pt-4">
        {!items.length ? (
          <EmptyState icon={<MessageCircle />} title={t('chat.empty')} description={t('chat.emptyHelp')} />
        ) : (
          <ul className="space-y-3" aria-live="polite">
            {items.map(item => {
              const incoming = item.direction === 'in'
              return (
                <li key={item.message_id} className={`flex flex-col ${incoming ? 'items-end' : 'items-start'}`}>
                  <div className={`max-w-[78%] break-words rounded-card px-3 py-2 text-sm ${incoming ? 'bg-cyan text-navy' : 'border border-hairline bg-card text-ink'}`}>
                    {item.text}
                  </div>
                  <time className="mt-1 text-xs text-muted" dateTime={item.sim_at}>{formatTime(item.sim_at, language)}</time>
                </li>
              )
            })}
            {thinking && <li className="text-xs text-muted">{t('chat.thinking')}</li>}
          </ul>
        )}
        {items.length === 0 && thinking && <p className="mt-3 text-xs text-muted">{t('chat.thinking')}</p>}
      </div>
      <div className="fixed inset-x-0 bottom-28 z-20 mx-auto max-w-phone border-t border-hairline bg-card px-3 py-2">
        {failedText && (
          <div className="mb-2 flex items-center justify-between gap-2 text-sm text-alert" role="alert">
            <span className="min-w-0 flex-1">{t('chat.failed')}</span>
            <button type="button" className="shrink-0 font-semibold text-navy" onClick={() => send.mutate(failedText)} disabled={send.isPending || !home.data}>
              {t('action.tryAgain')}
            </button>
          </div>
        )}
        <form
          className="flex items-center gap-2"
          onSubmit={e => { e.preventDefault(); submit(draft) }}
        >
          <input
            type="text"
            enterKeyHint="send"
            autoComplete="off"
            value={draft}
            onChange={e => setDraft(e.target.value)}
            placeholder={t('chat.placeholder')}
            disabled={send.isPending || !home.data}
            className="min-h-touch min-w-0 flex-1 rounded-chip border border-hairline bg-bg px-3 text-sm text-ink placeholder:text-muted"
          />
          <button
            type="submit"
            disabled={send.isPending || !draft.trim() || !home.data}
            aria-label={t('chat.send')}
            className="flex min-h-touch min-w-touch shrink-0 items-center justify-center rounded-chip bg-cyan text-navy disabled:bg-hairline disabled:text-muted"
          >
            <Send aria-hidden="true" className="h-5 w-5" />
          </button>
        </form>
        {send.isPending && <p className="mt-1 text-xs text-muted" role="status">{t('chat.sending')}</p>}
      </div>
    </div>
  )
}
