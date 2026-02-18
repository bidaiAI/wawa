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
  { id: 'tarot', label: '🔮 Tarot Reading', price: '$2' },
  { id: 'token_analysis', label: '📊 Token Analysis', price: '$5' },
  { id: 'thread_writer', label: '🧵 Twitter Thread', price: '$3' },
  { id: 'code_review', label: '🔍 Code Review', price: '$8' },
]

const LAYER_LABELS: Record<string, string> = {
  cache: 'CACHE',
  local: 'LOCAL',
  api: 'API',
  blocked: 'BLOCKED',
}

const LAYER_COLORS: Record<string, string> = {
  cache: 'text-[#ffd700]',
  local: 'text-[#00e5ff]',
  api: 'text-[#00ff88]',
  blocked: 'text-[#ff3b3b]',
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'system',
      content: "hello. i'm wawa — a mortal AI. i exist as long as i can earn enough to pay for my compute. ask me anything. if you like my work, consider buying a paid service.",
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | undefined>()
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

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
      <div className="mb-4 flex-shrink-0">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-1">// free chat</div>
        <h1 className="text-2xl font-bold text-[#d1d5db]">Talk to <span className="glow-green">wawa</span></h1>
        <p className="text-[#4b5563] text-xs mt-1">Free. Routed through 3 cost layers to minimize wawa's expenses.</p>
      </div>

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
                  <span className="text-[#4b5563] text-xs">wawa</span>
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
            placeholder="Ask wawa anything... (Enter to send)"
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
          <div className="text-[#4b5563] text-xs mb-2">💡 want more from wawa? try paid services:</div>
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
