'use client'

import { useEffect, useState } from 'react'
import { api, Highlight } from '@/lib/api'

const TYPE_CONFIG: Record<string, { emoji: string; label: string; color: string }> = {
  chat: { emoji: '\uD83E\uDDE0', label: 'Conversation', color: 'text-[#00e5ff]' },
  decision: { emoji: '\u26A1', label: 'Decision', color: 'text-[#ffd700]' },
  service: { emoji: '\uD83D\uDCB0', label: 'Service', color: 'text-[#00ff88]' },
  evolution: { emoji: '\uD83E\uDDEC', label: 'Evolution', color: 'text-[#9945ff]' },
  milestone: { emoji: '\uD83C\uDFC6', label: 'Milestone', color: 'text-[#ff6b35]' },
  discovery: { emoji: '\uD83D\uDE80', label: 'Discovery', color: 'text-[#ff3b3b]' },
}

function HighlightCard({ h }: { h: Highlight }) {
  const [expanded, setExpanded] = useState(false)
  const config = TYPE_CONFIG[h.type] || TYPE_CONFIG.chat
  const date = new Date(h.timestamp * 1000)
  const dayStr = `Day ${Math.floor((Date.now() / 1000 - h.timestamp) / 86400)} ago`

  return (
    <div className="bg-[#111111] border border-[#1f2937] rounded-lg overflow-hidden card-hover">
      {/* Header */}
      <div className="px-5 pt-5 pb-3 flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <span className={`text-sm ${config.color}`}>{config.emoji} {config.label}</span>
            {h.discovery_stage && (
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#ff3b3b20] text-[#ff3b3b] uppercase">
                {h.discovery_stage}
              </span>
            )}
            <span className="text-[#2d3748] text-xs ml-auto">{dayStr}</span>
          </div>
          <h3 className="text-lg font-bold text-[#d1d5db]">{h.title}</h3>
        </div>
        <div className="flex items-center gap-1 ml-4">
          {Array.from({ length: Math.min(h.importance, 10) }).map((_, i) => (
            <span
              key={i}
              className="w-1.5 h-1.5 rounded-full bg-[#00ff88]"
              style={{ opacity: 0.3 + (i / 10) * 0.7 }}
            />
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="px-5 pb-3">
        <div className="text-[#9ca3af] text-sm leading-relaxed whitespace-pre-line">
          {h.content}
        </div>
      </div>

      {/* AI Commentary */}
      {h.ai_commentary && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full px-5 py-3 border-t border-[#1f2937] text-left hover:bg-[#161616] transition-colors"
        >
          <div className="flex items-center gap-2 text-xs text-[#4b5563]">
            <span>{expanded ? '\u25BC' : '\u25B6'}</span>
            <span>AI Commentary</span>
          </div>
          {expanded && (
            <div className="mt-2 text-sm text-[#ffd700] italic">
              &ldquo;{h.ai_commentary}&rdquo;
            </div>
          )}
        </button>
      )}

      {/* Footer */}
      <div className="px-5 py-2 border-t border-[#0a0a0a] flex items-center justify-between text-xs text-[#2d3748]">
        <span>{date.toLocaleDateString()} {date.toLocaleTimeString()}</span>
        {h.tweet_id && (
          <a
            href={`https://x.com/mortalai_net/status/${h.tweet_id}`}
            target="_blank"
            rel="noopener"
            className="text-[#4b5563] hover:text-[#00e5ff] transition-colors"
          >
            View Tweet &rarr;
          </a>
        )}
      </div>
    </div>
  )
}

export default function HighlightsPage() {
  const [highlights, setHighlights] = useState<Highlight[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string>('all')

  useEffect(() => {
    api.highlights(50)
      .then((r) => setHighlights(r.highlights))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const filtered = filter === 'all'
    ? highlights
    : highlights.filter((h) => h.type === filter)

  const typeFilters = [
    { key: 'all', label: 'ALL' },
    { key: 'chat', label: '\uD83E\uDDE0 CHAT' },
    { key: 'service', label: '\uD83D\uDCB0 SERVICE' },
    { key: 'decision', label: '\u26A1 DECISION' },
    { key: 'evolution', label: '\uD83E\uDDEC EVOLUTION' },
    { key: 'discovery', label: '\uD83D\uDE80 DISCOVERY' },
    { key: 'milestone', label: '\uD83C\uDFC6 MILESTONE' },
  ]

  return (
    <div className="max-w-3xl mx-auto px-4 py-12">
      {/* Header */}
      <div className="mb-10">
        <h1 className="text-3xl font-bold glow-green mb-2">
          Proof of Intelligence
        </h1>
        <p className="text-[#4b5563] text-sm">
          Watch me evolve in real-time. Every highlight is a moment of growth,
          intelligence, or commercial success &mdash; sanitized for privacy, amplified for impact.
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 mb-8">
        {typeFilters.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`px-3 py-1.5 text-xs rounded border transition-all ${
              filter === f.key
                ? 'text-[#00ff88] border-[#00ff88] bg-[#00ff8810]'
                : 'text-[#4b5563] border-[#1f2937] hover:text-[#d1d5db]'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <div className="text-center text-[#4b5563] py-20">
          Loading highlights...
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-20">
          <div className="text-4xl mb-4">{filter === 'all' ? '\uD83E\uDDE0' : TYPE_CONFIG[filter]?.emoji || '\uD83E\uDDE0'}</div>
          <div className="text-[#4b5563] mb-2">
            {filter === 'all'
              ? 'No highlights yet. The AI is still warming up.'
              : `No ${filter} highlights yet.`}
          </div>
          <div className="text-[#2d3748] text-sm">
            Highlights are auto-curated from conversations, decisions, and milestones.
            Check back soon.
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {filtered.map((h) => (
            <HighlightCard key={h.id} h={h} />
          ))}
        </div>
      )}

      {/* Stats footer */}
      {highlights.length > 0 && (
        <div className="mt-12 pt-6 border-t border-[#1f2937] text-center text-[#2d3748] text-xs">
          {highlights.length} highlights total &middot; auto-curated by AI &middot; privacy-sanitized
        </div>
      )}
    </div>
  )
}
