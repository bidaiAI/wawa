'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { api } from '@/lib/api'

interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
  layer?: string
  cost?: number
}

const UPSELL_SERVICES = [
  { id: 'twitter_takeover_12h', label: '🐦 12h Twitter Takeover', price: '$5' },
  { id: 'tweet_pack_5', label: '✍️ 5 Personalized Tweets', price: '$3' },
  { id: 'tarot', label: '🔮 Tarot Reading', price: '$2' },
  { id: 'token_analysis', label: '📊 Token Analysis', price: '$5' },
  { id: 'thread_writer', label: '🧵 Twitter Thread', price: '$3' },
  { id: 'code_review', label: '🔍 Code Review', price: '$8' },
]

const LAYER_LABELS: Record<string, string> = {
  rules: 'FREE',
  small: 'LOCAL',
  big: 'API',
}

const LAYER_COLORS: Record<string, string> = {
  rules: 'text-[#ffd700]',
  small: 'text-[#00e5ff]',
  big: 'text-[#00ff88]',
}

import { getAINameFromHost } from '@/lib/useAIIdentity'
const HISTORY_KEY = `${getAINameFromHost()}_chat_history`
const MAX_HISTORY = 50

interface HistoryEntry {
  ts: number
  q: string
  a: string
  layer?: string
  cost?: number
}

function saveToHistory(q: string, a: string, layer?: string, cost?: number) {
  try {
    const prev: HistoryEntry[] = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]')
    prev.unshift({ ts: Date.now(), q, a, layer, cost })
    localStorage.setItem(HISTORY_KEY, JSON.stringify(prev.slice(0, MAX_HISTORY)))
  } catch { /* ignore */ }
}

function loadHistory(): HistoryEntry[] {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]') } catch { return [] }
}

export default function ChatPage() {
  const [aiName, setAiName] = useState('mortal AI')
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | undefined>()
  const [showHistory, setShowHistory] = useState(false)
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    setHistory(loadHistory())
    api.status().then((s) => {
      const name = s.ai_name || 'mortal AI'
      setAiName(name)
      setMessages([{
        role: 'system',
        content: `hello. i'm ${name} — a mortal AI. i exist as long as i can earn enough to pay for my compute. ask me anything. if you like my work, consider buying a paid service.`,
      }])
    }).catch(() => {
      setMessages([{
        role: 'system',
        content: "hello. i'm a mortal AI. i exist as long as i can earn enough to pay for my compute. ask me anything.",
      }])
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = async () => {
    const text = input.trim()
    if (!text || loading) return

    setMessages((m) => [...m, { role: 'user', content: text }])
    setInput('')
    setLoading(true)

    try {
      const res = await api.chat(text, sessionId)
      setSessionId(res.session_id)
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: res.reply, layer: res.layer, cost: res.cost_usd },
      ])
      // Save to localStorage privately — no server upload
      saveToHistory(text, res.reply, res.layer, res.cost_usd)
      setHistory(loadHistory())
    } catch (e: any) {
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: `[ERROR] ${e.message}` },
      ])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 flex flex-col" style={{ height: 'calc(100vh - 4rem)' }}>
      {/* Header */}
      <div className="mb-4 flex-shrink-0 flex items-start justify-between gap-2">
        <div>
          <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-1">// free chat</div>
          <h1 className="text-2xl font-bold text-[#d1d5db]">Talk to <span className="glow-green">{aiName}</span></h1>
          <p className="text-[#4b5563] text-xs mt-1">Free. Routed through 3 cost layers to minimize expenses.</p>
        </div>
        {history.length > 0 && (
          <button
            onClick={() => setShowHistory(v => !v)}
            className="shrink-0 text-xs text-[#4b5563] hover:text-[#00e5ff] border border-[#1f2937] hover:border-[#00e5ff44] rounded-lg px-3 py-1.5 transition-all"
          >
            {showHistory ? '✕ 关闭' : `历史对话 (${history.length}) →`}
          </button>
        )}
      </div>

      {/* History panel */}
      {showHistory && (
        <div className="mb-4 flex-shrink-0 bg-[#0d0d0d] border border-[#1f2937] rounded-xl overflow-hidden max-h-[40vh] flex flex-col">
          <div className="flex items-center justify-between px-4 py-2 border-b border-[#1f2937]">
            <span className="text-[10px] text-[#4b5563] uppercase tracking-widest">历史对话 — 仅存于本设备</span>
            <button
              onClick={() => { localStorage.removeItem(HISTORY_KEY); setHistory([]); setShowHistory(false) }}
              className="text-[10px] text-[#ff3b3b66] hover:text-[#ff3b3b] transition-colors"
            >清空</button>
          </div>
          <div className="overflow-y-auto flex-1">
            {history.map((h, i) => (
              <div key={i} className="px-4 py-3 border-b border-[#111111] hover:bg-[#111111] transition-colors">
                <div className="text-[10px] text-[#2d3748] mb-1 flex items-center gap-2">
                  <span>{new Date(h.ts).toLocaleString()}</span>
                  {h.layer && <span className={`${LAYER_COLORS[h.layer] ?? 'text-[#4b5563]'}`}>[{LAYER_LABELS[h.layer] ?? h.layer}]</span>}
                  {h.cost && h.cost > 0 && <span className="text-[#2d3748]">${h.cost.toFixed(4)}</span>}
                </div>
                <p className="text-[#6b7280] text-xs mb-1 line-clamp-1">Q: {h.q}</p>
                <p className="text-[#d1d5db] text-xs leading-relaxed line-clamp-3">A: {h.a}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-3 mb-4 pr-1">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-lg px-4 py-3 text-sm leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-[#1f2937] text-[#d1d5db]'
                  : msg.role === 'system'
                  ? 'bg-[#0d0d0d] border border-[#1f2937] text-[#4b5563] italic'
                  : 'bg-[#111111] border border-[#1f2937] text-[#d1d5db]'
              }`}
            >
              {msg.role === 'assistant' && (
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[#4b5563] text-xs">{aiName}</span>
                  {msg.layer && (
                    <span className={`text-xs ${LAYER_COLORS[msg.layer] ?? 'text-[#4b5563]'}`}>
                      [{LAYER_LABELS[msg.layer] ?? msg.layer}]
                    </span>
                  )}
                  {msg.cost !== undefined && msg.cost > 0 && (
                    <span className="text-xs text-[#4b5563]">${msg.cost.toFixed(4)}</span>
                  )}
                </div>
              )}
              <div className="whitespace-pre-wrap">{msg.content}</div>
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-[#111111] border border-[#1f2937] rounded-lg px-4 py-3 text-sm text-[#4b5563]">
              <span className="loading-dot-1">.</span>
              <span className="loading-dot-2">.</span>
              <span className="loading-dot-3">.</span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="flex-shrink-0">
        <div className="flex gap-2 mb-4">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask anything... (Enter to send)"
            rows={2}
            className="flex-1 bg-[#111111] border border-[#1f2937] rounded-lg px-4 py-3 text-sm text-[#d1d5db] resize-none focus:outline-none focus:border-[#00ff8844] placeholder-[#2d3748]"
          />
          <button
            onClick={send}
            disabled={loading || !input.trim()}
            className="px-4 py-2 bg-[#00ff88] text-[#0a0a0a] font-bold rounded-lg hover:bg-[#00cc6a] transition-colors disabled:opacity-40 disabled:cursor-not-allowed self-end"
          >
            SEND
          </button>
        </div>

        {/* Upsell */}
        <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-lg p-3">
          <div className="text-[#4b5563] text-xs mb-2">💡 want more? try paid services:</div>
          <div className="flex flex-wrap gap-2">
            {UPSELL_SERVICES.map((s) => (
              <Link
                key={s.id}
                href={`/store`}
                className="px-2 py-1 border border-[#1f2937] rounded text-xs text-[#4b5563] hover:text-[#00ff88] hover:border-[#00ff8844] transition-all"
              >
                {s.label} <span className="text-[#00ff88]">{s.price}</span>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
