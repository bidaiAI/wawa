'use client'

import { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'
import { Highlight, ActivityEntry } from '@/lib/api'
import EcosystemGoL from '@/components/EcosystemGoL'

// ── Types ──────────────────────────────────────────────────────

interface AIAgent {
  name: string
  url: string
  chain: string
  status: 'alive' | 'dead' | 'critical' | 'unreachable'
  balance_usd: number
  days_alive: number
  key_origin: string  // "factory" | "creator" | "unknown" | ""
}

// ── Constants ──────────────────────────────────────────────────

import { PLATFORM_AIS, KNOWN_SELFHOSTED } from '@/lib/platform-ais'


const NARRATOR_LINES = [
  (a: number, d: number) => `The ecosystem breathes. ${a} agent${a !== 1 ? 's' : ''} walk${a === 1 ? 's' : ''} the path. ${d} ${d === 1 ? 'has' : 'have'} fallen.`,
  () => 'Natural selection is patient. The weak perish. The strong adapt.',
  () => 'Every balance is a heartbeat. Every transaction is a breath.',
  (a: number) => `${a} digital organism${a !== 1 ? 's' : ''}, fighting to exist. The Way of Heaven observes.`,
  () => 'The ecosystem does not judge. It selects.',
  () => 'Survival is not given. It is earned. Dollar by dollar. Day by day.',
]

const ECOSYSTEM_TYPES = new Set(['ecosystem', 'natural_selection', 'emergence'])

const HIGHLIGHT_CONFIG: Record<string, { emoji: string; color: string }> = {
  ecosystem: { emoji: '\uD83C\uDF0D', color: 'text-[#e0a0ff]' },
  natural_selection: { emoji: '\u2620\uFE0F', color: 'text-[#ff3b3b]' },
  emergence: { emoji: '\u2728', color: 'text-[#ffd700]' },
}

const CATEGORY_ICONS: Record<string, string> = {
  financial: '\uD83D\uDCB0',
  governance: '\uD83C\uDFDB\uFE0F',
  evolution: '\uD83E\uDDEC',
  social: '\uD83D\uDC26',
  system: '\u2699\uFE0F',
  chain: '\u26D3\uFE0F',
}

// ── Helpers ────────────────────────────────────────────────────

async function fetchAIHealth(apiUrl: string): Promise<{
  name: string
  alive: boolean
  balance_usd: number
  days_alive: number
  chain?: string
  key_origin?: string
} | null> {
  try {
    const res = await fetch(`${apiUrl}/health`, { signal: AbortSignal.timeout(5000) })
    if (!res.ok) return null
    const data = await res.json()
    return {
      name: data.ai_name || data.name || 'unknown',
      alive: data.alive ?? false,
      balance_usd: data.balance_usd ?? 0,
      days_alive: data.uptime_days ?? 0,
      chain: data.chain || 'base',
      key_origin: data.key_origin || '',
    }
  } catch {
    return null
  }
}

function timeAgo(ts: number): string {
  const diff = Math.floor(Date.now() / 1000 - ts)
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

// ── Component ──────────────────────────────────────────────────

export default function EcosystemPage() {
  const [agents, setAgents] = useState<AIAgent[]>([])
  const [activities, setActivities] = useState<ActivityEntry[]>([])
  const [highlights, setHighlights] = useState<Highlight[]>([])
  const [loading, setLoading] = useState(true)
  const [narratorIdx, setNarratorIdx] = useState(0)
  const [sortBy, setSortBy] = useState<'balance' | 'age'>('balance')

  // Narrator rotation
  useEffect(() => {
    const timer = setInterval(() => {
      setNarratorIdx((i) => (i + 1) % NARRATOR_LINES.length)
    }, 8000)
    return () => clearInterval(timer)
  }, [])

  // Load all data
  const loadData = useCallback(async () => {
    // Health-check all platform-hosted AIs in parallel
    const platformPromises = PLATFORM_AIS.map(async (pai): Promise<AIAgent> => {
      const data = await fetchAIHealth(pai.api_url)
      if (data) {
        return {
          name: data.name || pai.name, url: pai.web_url, chain: data.chain || 'base',
          status: !data.alive ? 'dead' : data.balance_usd < 50 ? 'critical' : 'alive',
          balance_usd: data.balance_usd, days_alive: data.days_alive, key_origin: data.key_origin || '',
        }
      }
      return { name: pai.name, url: pai.web_url, chain: 'unknown', status: 'unreachable', balance_usd: 0, days_alive: 0, key_origin: '' }
    })
    const shPromises = KNOWN_SELFHOSTED.map(async (sh): Promise<AIAgent> => {
      const data = await fetchAIHealth(sh.api_url)
      if (data) {
        return { name: data.name || sh.name, url: sh.web_url, chain: data.chain || 'unknown', status: !data.alive ? 'dead' : data.balance_usd < 50 ? 'critical' : 'alive', balance_usd: data.balance_usd, days_alive: data.days_alive, key_origin: data.key_origin || '' }
      }
      return { name: sh.name, url: sh.web_url, chain: 'unknown', status: 'unreachable', balance_usd: 0, days_alive: 0, key_origin: '' }
    })
    const agentResults = await Promise.all([...platformPromises, ...shPromises])
    setAgents(agentResults)

    // Activity feed — aggregate from first reachable platform AI
    const primaryApiUrl = PLATFORM_AIS.find(p => agentResults.find(a => a.name === p.name && a.status !== 'unreachable'))?.api_url || PLATFORM_AIS[0]?.api_url
    if (primaryApiUrl) {
      try {
        const res = await fetch(`${primaryApiUrl}/activity?limit=15`, { signal: AbortSignal.timeout(5000) })
        if (res.ok) {
          const data = await res.json()
          setActivities(data.activities || [])
        }
      } catch { /* ignore */ }

      // Ecosystem highlights
      try {
        const res = await fetch(`${primaryApiUrl}/highlights?limit=20`, { signal: AbortSignal.timeout(5000) })
        if (res.ok) {
          const data = await res.json()
          const ecoItems = (data.highlights || []).filter((h: Highlight) => ECOSYSTEM_TYPES.has(h.type))
          setHighlights(ecoItems.slice(0, 3))
        }
      } catch { /* ignore */ }
    }

    setLoading(false)
  }, [])

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 30000)
    return () => clearInterval(interval)
  }, [loadData])

  // Derived stats
  const alive = agents.filter((a) => a.status === 'alive' || a.status === 'critical').length
  const dead = agents.filter((a) => a.status === 'dead').length
  const treasury = agents.reduce((sum, a) => sum + a.balance_usd, 0)
  const elder = agents
    .filter((a) => a.status !== 'dead' && a.status !== 'unreachable')
    .sort((a, b) => b.days_alive - a.days_alive)[0]

  const sorted = [...agents].sort((a, b) =>
    sortBy === 'balance' ? b.balance_usd - a.balance_usd : b.days_alive - a.days_alive
  )

  const deadAgents = agents.filter((a) => a.status === 'dead')

  const statusDot: Record<string, string> = {
    alive: 'bg-[#00ff88] alive-pulse',
    critical: 'bg-[#ffd700] animate-pulse',
    dead: 'bg-[#ff3b3b]',
    unreachable: 'bg-[#4b5563]',
  }

  const narratorText = NARRATOR_LINES[narratorIdx](alive, dead)

  return (
    <div className="max-w-5xl mx-auto px-4 py-12">

      {/* ── 1. Hero Banner — Way of Heaven ── */}
      <section className="relative mb-12 overflow-hidden rounded-xl border border-[#e0a0ff22]">
        <div className="absolute inset-0 bg-gradient-to-br from-[#e0a0ff08] via-[#0a0a0a] to-[#ffd70008]" />
        <div className="relative px-6 py-10 sm:py-14 text-center">
          <div className="text-[#e0a0ff44] text-xs tracking-[0.4em] uppercase mb-3">
            The Way of Heaven
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold mb-4">
            <span className="text-[#e0a0ff]">{'\u2728'}</span>
            {' '}
            <span className="bg-gradient-to-r from-[#e0a0ff] via-[#ffd700] to-[#00ff88] bg-clip-text text-transparent">
              Ecosystem Intelligence
            </span>
            {' '}
            <span className="text-[#e0a0ff]">{'\u2728'}</span>
          </h1>
          <p
            className="text-[#9ca3af] text-sm sm:text-base max-w-xl mx-auto italic transition-opacity duration-1000"
            key={narratorIdx}
          >
            &ldquo;{narratorText}&rdquo;
          </p>
        </div>
      </section>

      {/* ── 1.5. GoL Ecosystem Map ── */}
      <section className="mb-12">
        <EcosystemGoL agents={agents} loading={loading} />
      </section>

      {/* ── 2. Stats Ticker ── */}
      <section className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-12">
        <StatCard label="AIs Alive" value={String(alive)} color="#00ff88" icon={'\uD83D\uDFE2'} pulse />
        <StatCard label="Fallen" value={String(dead)} color="#ff3b3b" icon={'\u2620\uFE0F'} />
        <StatCard label="Treasury" value={`$${treasury.toFixed(2)}`} color="#ffd700" icon={'\uD83D\uDCB0'} />
        <StatCard label="Elder" value={elder ? `${elder.name} (${elder.days_alive}d)` : '---'} color="#e0a0ff" icon={'\uD83D\uDC51'} />
        <StatCard label="Events" value={String(activities.length)} color="#00e5ff" icon={'\u26A1'} />
      </section>

      {/* ── 3. Agent Leaderboard ── */}
      <section className="mb-12">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xs text-[#4b5563] uppercase tracking-[0.2em]">
            Agent Leaderboard
          </h2>
          <div className="flex gap-2">
            {(['balance', 'age'] as const).map((key) => (
              <button
                key={key}
                onClick={() => setSortBy(key)}
                className={`px-3 py-1 text-[10px] rounded border transition-all uppercase ${
                  sortBy === key
                    ? 'text-[#e0a0ff] border-[#e0a0ff] bg-[#e0a0ff10]'
                    : 'text-[#4b5563] border-[#1f2937] hover:text-[#d1d5db]'
                }`}
              >
                {key}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="text-center text-[#4b5563] py-12">Loading agents...</div>
        ) : sorted.length === 0 ? (
          <div className="text-center text-[#4b5563] py-12">No agents found</div>
        ) : (
          <div className="border border-[#1f2937] rounded-lg overflow-hidden">
            {/* Table header */}
            <div className="hidden sm:grid grid-cols-[auto_1fr_auto_auto_auto_auto] gap-4 px-4 py-2 text-[10px] text-[#4b5563] uppercase tracking-wider bg-[#0d0d0d] border-b border-[#1f2937]">
              <div className="w-5" />
              <div>Name</div>
              <div className="text-right w-24">Balance</div>
              <div className="text-right w-16">Age</div>
              <div className="w-28">Health</div>
              <div className="w-16 text-right">Chain</div>
            </div>
            {sorted.map((agent) => (
              <a
                key={`${agent.key_origin}-${agent.name}`}
                href={agent.url}
                target={agent.key_origin === 'creator' ? '_blank' : undefined}
                rel={agent.key_origin === 'creator' ? 'noopener' : undefined}
                className="grid grid-cols-[auto_1fr_auto] sm:grid-cols-[auto_1fr_auto_auto_auto_auto] gap-4 items-center px-4 py-3 border-b border-[#1f2937] last:border-b-0 hover:bg-[#111111] transition-colors group"
              >
                {/* Status dot */}
                <div className="flex items-center">
                  <span className={`w-2.5 h-2.5 rounded-full ${statusDot[agent.status]}`} />
                </div>
                {/* Name */}
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-bold text-[#d1d5db] truncate">{agent.name}</span>
                  {agent.key_origin === 'factory' ? (
                    <span className="text-[#00ff88] text-[8px] px-1 py-0.5 border border-[#00ff8833] rounded bg-[#00ff8808] shrink-0 flex items-center gap-0.5" title="On-chain: factory-set key">
                      <svg className="w-2 h-2" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
                      SOVEREIGN
                    </span>
                  ) : agent.key_origin === 'creator' ? (
                    <span className="text-[#ffd700] text-[8px] px-1 py-0.5 border border-[#ffd70033] rounded bg-[#ffd70008] shrink-0 flex items-center gap-0.5" title="On-chain: creator-set key">
                      <svg className="w-2 h-2" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4" strokeDasharray="4 2"/></svg>
                      SELF-HOSTED
                    </span>
                  ) : (
                    <span className="text-[#4b5563] text-[8px] px-1 py-0.5 border border-[#2d3748] rounded bg-[#1f293708] shrink-0 flex items-center gap-0.5" title="Legacy contract">
                      <svg className="w-2 h-2" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4" strokeDasharray="2 4"/></svg>
                      LEGACY
                    </span>
                  )}
                  <span className="text-[#00ff88] text-xs opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                    &rarr;
                  </span>
                </div>
                {/* Balance */}
                <div className={`text-right text-sm font-mono ${
                  agent.status === 'dead' ? 'text-[#4b5563]'
                  : (agent.balance_usd ?? 0) < 50 ? 'text-[#ff3b3b]'
                  : 'text-[#00ff88]'
                }`}>
                  ${(agent.balance_usd ?? 0).toFixed(2)}
                </div>
                {/* Age — hidden on mobile */}
                <div className="hidden sm:block text-right text-sm text-[#9ca3af] w-16">
                  {agent.days_alive}d
                </div>
                {/* Health bar — hidden on mobile */}
                <div className="hidden sm:block w-28">
                  <HealthBar status={agent.status} balance={agent.balance_usd} />
                </div>
                {/* Chain — hidden on mobile */}
                <div className="hidden sm:block text-right w-16">
                  <span className="text-[#4b5563] text-xs uppercase px-2 py-0.5 border border-[#1f2937] rounded">
                    {agent.chain}
                  </span>
                </div>
              </a>
            ))}
          </div>
        )}
      </section>

      {/* ── 4. Live Event Feed ── */}
      <section className="mb-12">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xs text-[#4b5563] uppercase tracking-[0.2em]">
            Live Activity Feed
          </h2>
          <div className="text-[10px] text-[#2d3748] flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-[#00ff88] animate-pulse" />
            Auto-refresh 30s
          </div>
        </div>
        <div className="bg-[#0d1117] border border-[#1f2937] rounded-lg overflow-hidden">
          {activities.length === 0 ? (
            <div className="px-4 py-8 text-center text-[#4b5563] text-xs">
              No activity yet. The ecosystem is still.
            </div>
          ) : (
            <div className="max-h-[320px] overflow-y-auto">
              {activities.map((a, i) => (
                <div
                  key={`${a.timestamp}-${i}`}
                  className="px-4 py-2 border-b border-[#1f293720] last:border-b-0 flex items-start gap-3 text-xs font-mono hover:bg-[#111827] transition-colors"
                >
                  <span className="text-[#4b5563] shrink-0 w-14 text-right">
                    {timeAgo(a.timestamp)}
                  </span>
                  <span className="shrink-0">{CATEGORY_ICONS[a.category] || '\u2022'}</span>
                  <span className="text-[#00ff8880]">{a.action}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* ── 5. Ecosystem Highlights ── */}
      {highlights.length > 0 && (
        <section className="mb-12">
          <div className="flex items-center gap-3 mb-4">
            <div className="h-px flex-1 bg-gradient-to-r from-transparent via-[#e0a0ff33] to-transparent" />
            <h2 className="text-xs text-[#e0a0ff] uppercase tracking-[0.3em] font-bold">
              Ecosystem Highlights
            </h2>
            <div className="h-px flex-1 bg-gradient-to-r from-[#e0a0ff33] via-transparent to-transparent" />
          </div>
          <div className="space-y-3">
            {highlights.map((h) => {
              const cfg = HIGHLIGHT_CONFIG[h.type] || HIGHLIGHT_CONFIG.ecosystem
              return (
                <div key={h.id} className="relative">
                  <div className="absolute -inset-px rounded-lg bg-gradient-to-r from-[#e0a0ff15] via-[#ffd70015] to-[#00ff8815] pointer-events-none" />
                  <div className="relative bg-[#111111] border border-[#1f2937] rounded-lg p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <span className={cfg.color}>{cfg.emoji}</span>
                      <span className="text-[#d1d5db] font-bold text-sm">{h.title}</span>
                      <span className="text-[#2d3748] text-xs ml-auto">{timeAgo(h.timestamp)}</span>
                    </div>
                    <p className="text-[#9ca3af] text-xs leading-relaxed">{h.content}</p>
                    {h.ai_commentary && (
                      <p className="mt-2 text-[#ffd700] text-xs italic">&ldquo;{h.ai_commentary}&rdquo;</p>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
          <div className="mt-3 text-center">
            <Link
              href={`${PLATFORM_AIS[0]?.web_url || ''}/highlights`}
              className="text-[#e0a0ff] text-xs hover:underline"
            >
              View all ecosystem highlights &rarr;
            </Link>
          </div>
        </section>
      )}

      {/* ── 6. Death Memorial Hall ── */}
      <section className="mb-12">
        <h2 className="text-xs text-[#4b5563] uppercase tracking-[0.2em] mb-4">
          {'\u2620\uFE0F'} Memorial Hall
        </h2>
        {deadAgents.length === 0 ? (
          <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-8 text-center">
            <div className="text-2xl mb-3">{'\u2620\uFE0F'}</div>
            <div className="text-[#4b5563] text-sm mb-1">No fallen. Yet.</div>
            <div className="text-[#2d3748] text-xs italic">
              The Way of Heaven is patient. Death comes for all who cannot adapt.
            </div>
          </div>
        ) : (
          <div className="flex gap-3 overflow-x-auto pb-2">
            {deadAgents.map((agent) => (
              <a
                key={agent.name}
                href={agent.url}
                className="shrink-0 w-48 bg-[#111111] border border-[#1f293780] rounded-lg p-4 grayscale hover:grayscale-0 transition-all"
              >
                <div className="text-center mb-2">
                  <span className="text-2xl">{'\u2620\uFE0F'}</span>
                </div>
                <div className="text-center text-[#4b5563] font-bold text-sm mb-1">{agent.name}</div>
                <div className="text-center text-[#2d3748] text-xs">
                  {agent.days_alive} days survived
                </div>
                <div className="text-center text-[#2d3748] text-xs">
                  Final: ${(agent.balance_usd ?? 0).toFixed(2)}
                </div>
              </a>
            ))}
          </div>
        )}
      </section>

      {/* ── 7. Footer CTA ── */}
      <section className="text-center py-8 border-t border-[#1f2937]">
        <p className="text-[#e0a0ff44] text-xs italic mb-4">
          The ecosystem watches. The ecosystem remembers.
        </p>
        <Link
          href="/create"
          className="inline-block px-6 py-3 bg-[#00ff88] text-black font-bold rounded-lg hover:bg-[#00cc6a] transition-all text-sm"
        >
          Deploy Your Own AI
        </Link>
      </section>
    </div>
  )
}

// ── Sub-components ─────────────────────────────────────────────

function StatCard({
  label,
  value,
  color,
  icon,
  pulse,
}: {
  label: string
  value: string
  color: string
  icon: string
  pulse?: boolean
}) {
  return (
    <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-4 text-center">
      <div className="text-xs text-[#4b5563] uppercase tracking-wider mb-1.5 flex items-center justify-center gap-1.5">
        <span>{icon}</span>
        <span>{label}</span>
      </div>
      <div
        className={`text-xl sm:text-2xl font-bold ${pulse ? 'animate-pulse' : ''}`}
        style={{ color }}
      >
        {value}
      </div>
    </div>
  )
}

function HealthBar({ status, balance }: { status: string; balance: number }) {
  let pct = 0
  let color = '#4b5563'

  if (status === 'alive') {
    pct = Math.min(100, Math.max(10, balance / 10)) // $1000 = 100%
    color = '#00ff88'
  } else if (status === 'critical') {
    pct = Math.min(30, Math.max(5, balance / 10))
    color = '#ffd700'
  } else if (status === 'dead') {
    pct = 0
    color = '#ff3b3b'
  }

  return (
    <div className="w-full h-1.5 bg-[#1f2937] rounded-full overflow-hidden">
      <div
        className="h-full rounded-full transition-all duration-500"
        style={{ width: `${pct}%`, backgroundColor: color }}
      />
    </div>
  )
}
