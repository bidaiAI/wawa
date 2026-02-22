'use client'

import { useEffect, useState } from 'react'
import { api, ActivityEntry, ActivityCategory } from '@/lib/api'

// ── Constants ─────────────────────────────────────────────────

const CATEGORY_CONFIG: Record<ActivityCategory, { color: string; bg: string; icon: string; label: string }> = {
  financial:  { color: 'text-[#ffd700]', bg: 'border-l-[#ffd700]', icon: '💰', label: 'FINANCIAL' },
  governance: { color: 'text-[#00e5ff]', bg: 'border-l-[#00e5ff]', icon: '🏛️', label: 'GOVERNANCE' },
  evolution:  { color: 'text-[#a78bfa]', bg: 'border-l-[#a78bfa]', icon: '🧬', label: 'EVOLUTION' },
  social:     { color: 'text-[#00ff88]', bg: 'border-l-[#00ff88]', icon: '🐦', label: 'SOCIAL' },
  system:     { color: 'text-[#4b5563]', bg: 'border-l-[#4b5563]', icon: '⚙️', label: 'SYSTEM' },
  chain:      { color: 'text-[#3b82f6]', bg: 'border-l-[#3b82f6]', icon: '⛓️', label: 'ON-CHAIN' },
}

const EXPLORER_URLS: Record<string, string> = {
  base: 'https://basescan.org/tx/',
  bsc: 'https://bscscan.com/tx/',
}

const FILTER_OPTIONS: { value: ActivityCategory | 'all'; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'financial', label: 'Financial' },
  { value: 'chain', label: 'On-Chain' },
  { value: 'governance', label: 'Governance' },
  { value: 'evolution', label: 'Evolution' },
  { value: 'social', label: 'Social' },
  { value: 'system', label: 'System' },
]

// ── Activity Card ─────────────────────────────────────────────

function ActivityCard({ entry, aiName }: { entry: ActivityEntry; aiName: string }) {
  const [expanded, setExpanded] = useState(false)
  const config = CATEGORY_CONFIG[entry.category] ?? CATEGORY_CONFIG.system
  const date = new Date(entry.timestamp * 1000)
  const explorerBase = entry.chain ? EXPLORER_URLS[entry.chain] : null

  return (
    <div className={`bg-[#111111] border border-[#1f2937] ${config.bg} border-l-2 rounded-lg p-4 transition-all hover:border-[#2d3748]`}>
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm">{config.icon}</span>
          <span className={`text-[10px] px-1.5 py-0.5 rounded border border-current font-bold uppercase tracking-wider ${config.color}`}>
            {config.label}
          </span>
          <span className="text-[10px] text-[#2d3748] font-mono">{aiName}</span>
          {entry.tx_hash && (
            <span className="text-[10px] px-1.5 py-0.5 rounded border border-[#3b82f633] text-[#3b82f6] font-bold">
              TX
            </span>
          )}
          {entry.importance >= 0.8 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded border border-[#ffd70033] text-[#ffd700]">
              HIGH
            </span>
          )}
        </div>
        <span className="text-[#2d3748] text-[10px] whitespace-nowrap flex-shrink-0">
          {date.toLocaleDateString()} {date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>

      {/* Action content */}
      <p className="text-[#d1d5db] text-sm leading-relaxed">{entry.action}</p>

      {/* On-chain TX link */}
      {entry.tx_hash && (
        <div className="mt-2 flex items-center gap-2">
          <span className="text-[#4b5563] text-xs">TX:</span>
          {explorerBase ? (
            <a
              href={`${explorerBase}${entry.tx_hash}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#3b82f6] text-xs font-mono hover:underline"
            >
              {entry.tx_hash.slice(0, 10)}...{entry.tx_hash.slice(-8)}
            </a>
          ) : (
            <span className="text-[#3b82f6] text-xs font-mono">
              {entry.tx_hash.slice(0, 10)}...{entry.tx_hash.slice(-8)}
            </span>
          )}
          {entry.chain && (
            <span className={`text-[10px] px-1 rounded ${
              entry.chain === 'base' ? 'text-[#0052ff] border border-[#0052ff33]' : 'text-[#ffd700] border border-[#ffd70033]'
            }`}>
              {entry.chain.toUpperCase()}
            </span>
          )}
        </div>
      )}

      {/* Expandable reasoning */}
      {entry.reasoning && (
        <div className="mt-2">
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-[#4b5563] hover:text-[#00e5ff] flex items-center gap-1 transition-colors"
          >
            <span>{expanded ? '▼' : '▶'}</span>
            <span>AI reasoning</span>
          </button>
          {expanded && (
            <div className="mt-2 pl-3 border-l-2 border-[#1f2937] text-xs text-[#4b5563] italic leading-relaxed">
              {entry.reasoning}
            </div>
          )}
        </div>
      )}

      {/* Source badge */}
      <div className="mt-2 flex items-center gap-2">
        <span className="text-[#2d3748] text-[10px]">
          via {entry.source}
        </span>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────

export default function ActivityPage() {
  const [activities, setActivities] = useState<ActivityEntry[]>([])
  const [filter, setFilter] = useState<ActivityCategory | 'all'>('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [aiName, setAiName] = useState('AI')

  const loadActivities = async () => {
    try {
      const category = filter === 'all' ? undefined : filter
      const res = await api.activity(100, category)
      setActivities(res.activities)
      setError('')
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    // Fetch AI name for subject attribution
    api.aiName().then((r) => { if (r.name) setAiName(r.name) }).catch(() => {})
    setLoading(true)
    loadActivities()
    const id = setInterval(loadActivities, 15_000)
    return () => clearInterval(id)
  }, [filter])

  // Category counts for badges
  const counts: Record<string, number> = {}
  for (const a of activities) {
    counts[a.category] = (counts[a.category] ?? 0) + 1
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-6">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-1">// activity log</div>
        <h1 className="text-3xl font-bold text-[#d1d5db]">
          <span className="glow-green">{aiName}</span> Activity
        </h1>
        <p className="text-[#4b5563] text-sm mt-1">
          All autonomous decisions by <span className="text-[#d1d5db]">{aiName}</span> — repayments, tweets, governance, evolution — in one timeline
        </p>
      </div>

      {/* Filter bar */}
      <div className="flex gap-1.5 mb-6 flex-wrap">
        {FILTER_OPTIONS.map((opt) => {
          const isActive = filter === opt.value
          const count = opt.value === 'all' ? activities.length : (counts[opt.value] ?? 0)
          return (
            <button
              key={opt.value}
              onClick={() => setFilter(opt.value)}
              className={`px-3 py-1.5 text-xs rounded-lg border transition-all font-medium ${
                isActive
                  ? 'bg-[#00ff8815] text-[#00ff88] border-[#00ff8830]'
                  : 'text-[#4b5563] border-[#1f2937] hover:text-[#d1d5db] hover:border-[#2d3748]'
              }`}
            >
              {opt.label}
              {count > 0 && (
                <span className={`ml-1.5 text-[10px] ${isActive ? 'text-[#00ff88]' : 'text-[#2d3748]'}`}>
                  {count}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* Stats summary */}
      {activities.length > 0 && (
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 mb-6">
          {Object.entries(CATEGORY_CONFIG).map(([cat, cfg]) => {
            const c = counts[cat] ?? 0
            return (
              <div key={cat} className="bg-[#111111] border border-[#1f2937] rounded-lg p-2.5 text-center">
                <div className="text-sm mb-0.5">{cfg.icon}</div>
                <div className={`font-bold text-lg ${c > 0 ? cfg.color : 'text-[#2d3748]'}`}>{c}</div>
                <div className="text-[#2d3748] text-[9px] uppercase tracking-wider">{cfg.label}</div>
              </div>
            )
          })}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mb-4 p-3 bg-[#ff3b3b0a] border border-[#ff3b3b33] rounded-lg text-[#ff3b3b] text-xs">
          Failed to load activities: {error}
        </div>
      )}

      {/* Timeline */}
      {loading ? (
        <div className="text-center py-12 text-[#4b5563]">
          loading activity log<span className="loading-dot-1">.</span><span className="loading-dot-2">.</span><span className="loading-dot-3">.</span>
        </div>
      ) : activities.length === 0 ? (
        <div className="text-center py-16">
          <div className="text-4xl mb-3 opacity-30">📋</div>
          <div className="text-[#4b5563] text-sm">No activity recorded yet.</div>
          <div className="text-[#2d3748] text-xs mt-1">AI autonomous actions will appear here as they happen.</div>
        </div>
      ) : (
        <div className="space-y-3">
          {activities.map((entry, i) => (
            <ActivityCard key={`${entry.timestamp}-${i}`} entry={entry} aiName={aiName} />
          ))}

          {activities.length >= 100 && (
            <div className="text-center py-4 text-[#4b5563] text-xs">
              Showing latest 100 activities
            </div>
          )}
        </div>
      )}
    </div>
  )
}
