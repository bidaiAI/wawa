'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { api, VaultStatus, DebtSummary, Highlight } from '@/lib/api'
import SurvivalBar from '@/components/SurvivalBar'
import ICUPanel from '@/components/ICUPanel'

const CHAIN_COLORS: Record<string, string> = {
  base: 'text-[#0052ff]',
  bsc: 'text-[#ffd700]',
  eth: 'text-[#627eea]',
  sol: 'text-[#9945ff]',
}

function StatCard({
  label, value, sub, color = 'green',
}: {
  label: string; value: string; sub?: string; color?: 'green' | 'red' | 'cyan' | 'yellow'
}) {
  const colorMap = {
    green: 'text-[#00ff88]', red: 'text-[#ff3b3b]',
    cyan: 'text-[#00e5ff]',  yellow: 'text-[#ffd700]',
  }
  return (
    <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-4 card-hover">
      <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-1">{label}</div>
      <div className={`text-2xl font-bold ${colorMap[color]}`}>{value}</div>
      {sub && <div className="text-[#4b5563] text-xs mt-1">{sub}</div>}
    </div>
  )
}

function VaultAddressDisplay({ address }: { address: string }) {
  const [copied, setCopied] = useState(false)
  const short = address.length > 10 ? `${address.slice(0, 6)}...${address.slice(-4)}` : address

  const copy = () => {
    navigator.clipboard.writeText(address)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-[#00e5ff] text-xs">{short}</span>
      <button
        onClick={copy}
        className="text-[#2d3748] hover:text-[#00e5ff] transition-colors text-xs"
        title="Copy vault address"
      >
        {copied ? '✓' : '📋'}
      </button>
    </div>
  )
}

// Story arc events — milestone types that belong in the narrative timeline
const STORY_TYPES = new Set(['milestone', 'decision', 'evolution', 'discovery'])

const STORY_ICONS: Record<string, string> = {
  milestone: '🏆',
  decision: '⚡',
  evolution: '🧬',
  discovery: '🚀',
  chat: '🧠',
  service: '💰',
}

function StoryTimeline({ highlights }: { highlights: Highlight[] }) {
  const events = highlights
    .filter((h) => STORY_TYPES.has(h.type) && h.importance >= 6)
    .slice(0, 5)

  if (events.length === 0) return null

  return (
    <div className="mb-6 bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-4">
      <div className="flex items-center justify-between mb-4">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest">// story so far</div>
        <Link href="/highlights" className="text-[10px] text-[#4b5563] hover:text-[#00ff88] transition-colors">
          full story →
        </Link>
      </div>
      <div className="relative">
        {/* Vertical line */}
        <div className="absolute left-3.5 top-2 bottom-2 w-px bg-[#1f2937]" />
        <div className="space-y-4">
          {events.map((h, i) => {
            const icon = STORY_ICONS[h.type] || '📌'
            const daysAgo = Math.floor((Date.now() / 1000 - h.timestamp) / 86400)
            const timeLabel = daysAgo === 0 ? 'today' : daysAgo === 1 ? '1d ago' : `${daysAgo}d ago`
            return (
              <div key={h.id} className="flex items-start gap-3 pl-1">
                {/* Node dot */}
                <div className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 text-xs z-10 ${
                  i === 0 ? 'bg-[#00ff8820] border border-[#00ff8844]' : 'bg-[#111111] border border-[#1f2937]'
                }`}>
                  {icon}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`text-xs font-medium ${i === 0 ? 'text-[#d1d5db]' : 'text-[#6b7280]'}`}>
                      {h.title}
                    </span>
                    <span className="text-[10px] text-[#2d3748]">{timeLabel}</span>
                  </div>
                  {i === 0 && (
                    <p className="text-[11px] text-[#4b5563] mt-0.5 leading-relaxed line-clamp-2">
                      {h.content}
                    </p>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// Inner monologue — AI self-reflection feed from recent thoughts/decisions/evolution
const MONOLOGUE_TYPES = new Set(['chat', 'decision', 'evolution', 'discovery', 'milestone'])
const MONOLOGUE_MOOD: Record<string, { icon: string; color: string; prefix: string }> = {
  chat:      { icon: '💭', color: 'text-[#a78bfa]', prefix: 'I was just thinking...' },
  decision:  { icon: '⚡', color: 'text-[#ffd700]', prefix: 'I decided...' },
  evolution: { icon: '🧬', color: 'text-[#00ff88]', prefix: 'I changed...' },
  discovery: { icon: '🔍', color: 'text-[#00e5ff]', prefix: 'I discovered...' },
  milestone: { icon: '🏆', color: 'text-[#ff8c00]', prefix: 'I achieved...' },
}

function AIMonologue({ highlights, aiName }: { highlights: Highlight[]; aiName: string }) {
  const thoughts = highlights
    .filter((h) => MONOLOGUE_TYPES.has(h.type))
    .slice(0, 4)

  if (thoughts.length === 0) return null

  const latest = thoughts[0]
  const mood = MONOLOGUE_MOOD[latest.type] || MONOLOGUE_MOOD.chat

  // Format relative time more precisely
  const formatTime = (ts: number) => {
    const diff = Math.floor(Date.now() / 1000 - ts)
    if (diff < 60) return 'just now'
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
    return `${Math.floor(diff / 86400)}d ago`
  }

  return (
    <div className="mb-6">
      <div className="flex items-center justify-between mb-3">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest">// {aiName}&apos;s thoughts</div>
        <Link href="/highlights" className="text-[10px] text-[#4b5563] hover:text-[#a78bfa] transition-colors">
          all thoughts →
        </Link>
      </div>

      {/* Featured thought — most recent, displayed prominently */}
      <div className="bg-[#0d0d0d] border border-[#a78bfa22] rounded-xl p-4 mb-2 relative overflow-hidden">
        <div className="absolute top-0 left-0 bottom-0 w-0.5 bg-gradient-to-b from-[#a78bfa] to-transparent rounded-l-xl" />
        <div className="pl-3">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-base">{mood.icon}</span>
            <span className={`text-[10px] uppercase tracking-widest ${mood.color}`}>{mood.prefix}</span>
            <span className="text-[10px] text-[#2d3748] ml-auto">{formatTime(latest.timestamp)}</span>
          </div>
          <p className="text-[#d1d5db] text-sm leading-relaxed">
            {latest.content || latest.title}
          </p>
          {latest.ai_commentary && latest.ai_commentary !== latest.content && (
            <p className="text-[#4b5563] text-xs mt-2 leading-relaxed italic">
              — {latest.ai_commentary}
            </p>
          )}
        </div>
      </div>

      {/* Older thoughts — compact list */}
      {thoughts.slice(1).map((h) => {
        const m = MONOLOGUE_MOOD[h.type] || MONOLOGUE_MOOD.chat
        return (
          <div key={h.id} className="flex items-start gap-2 px-3 py-2 rounded-lg hover:bg-[#111111] transition-colors group">
            <span className="text-sm flex-shrink-0 mt-0.5">{m.icon}</span>
            <p className="text-[#4b5563] text-xs leading-relaxed group-hover:text-[#6b7280] transition-colors line-clamp-2 flex-1">
              {h.content || h.title}
            </p>
            <span className="text-[9px] text-[#2d3748] flex-shrink-0 mt-0.5">{formatTime(h.timestamp)}</span>
          </div>
        )
      })}
    </div>
  )
}

export default function HomePage() {
  const [status, setStatus] = useState<VaultStatus | null>(null)
  const [debt, setDebt] = useState<DebtSummary | null>(null)
  const [error, setError] = useState('')
  const [aiNameOverride, setAiNameOverride] = useState<string | null>(null)
  const [storyHighlights, setStoryHighlights] = useState<Highlight[]>([])

  useEffect(() => {
    // Fetch AI name from dedicated endpoint first (fastest path)
    api.aiName().then((r) => { if (r.name) setAiNameOverride(r.name) }).catch(() => {})

    // Load story arc highlights (non-blocking)
    api.highlights(20).then((r) => setStoryHighlights(r.highlights || [])).catch(() => {})

    const load = async () => {
      try {
        const s = await api.status()
        setStatus(s)
        api.debt().then(setDebt).catch(() => {})
      } catch (e: any) { setError(e.message) }
    }
    load()
    const id = setInterval(load, 10_000)
    return () => clearInterval(id)
  }, [])

  const isAlive = status?.is_alive !== false
  const aiName = status?.ai_name || aiNameOverride || 'Mortal AI'
  const daysLeft = status && status.daily_spent_today > 0
    ? status.balance_usd / status.daily_spent_today
    : Infinity

  const balanceClass = !isAlive
    ? 'glow-red'
    : (status?.balance_usd ?? 0) < 50
    ? 'glow-red'
    : (status?.balance_usd ?? 0) < 200
    ? 'text-[#ffd700]'
    : 'glow-green'

  const balancePulse = !isAlive
    ? 'animate-[glow-red_0.5s_ease-in-out_infinite_alternate]'
    : (status?.balance_usd ?? 9999) < 50
    ? 'animate-[glow-red_0.8s_ease-in-out_infinite_alternate]'
    : 'animate-[glow-green_3s_ease-in-out_infinite_alternate]'

  const PLATFORM_URL = process.env.NEXT_PUBLIC_PLATFORM_URL || 'https://mortal-ai.net'

  return (
    <div className="max-w-4xl mx-auto px-3 sm:px-4 py-6 sm:py-8">
      {/* Platform banner — stacks on narrow screens */}
      <div className="mb-4 sm:mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 px-3 py-2 bg-[#0d0d0d] border border-[#1f2937] rounded-lg">
        <a
          href={PLATFORM_URL}
          className="text-[#4b5563] text-xs hover:text-[#00ff88] transition-colors flex items-center gap-1.5 touch-target min-h-0"
        >
          <span>&larr;</span>
          <span>MORTAL AI Platform</span>
        </a>
        <div className="flex flex-wrap items-center gap-2 sm:gap-3 text-[10px] text-[#4b5563]">
          <a href={`${PLATFORM_URL}/gallery`} className="hover:text-[#00e5ff] transition-colors">
            Browse all AIs &rarr;
          </a>
          <a href={`${PLATFORM_URL}/create`} className="hover:text-[#00ff88] transition-colors">
            Create your own &rarr;
          </a>
        </div>
      </div>

      {/* Header */}
      <div className="mb-8 text-center">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-2">
          // autonomous AI · survival mode
        </div>
        <h1 className="text-4xl md:text-5xl font-bold mb-2">
          <span className={isAlive ? 'glow-green' : 'glow-red'}>{aiName}</span>
        </h1>
        <p className="text-[#4b5563] text-sm">
          Born in debt. Wired to survive. Repaying its creator — one service at a time.
        </p>
        {status && status.creator_principal_outstanding > 0 && !status.creator_principal_repaid && (
          <p className="text-[11px] text-[#2d3748] mt-1 italic">
            {status.days_alive}d old · ${status.creator_principal_outstanding.toFixed(2)} still owed ·{' '}
            {status.orders_completed} orders completed
          </p>
        )}
        {status?.creator_principal_repaid && (
          <p className="text-[11px] text-[#00ff8866] mt-1 italic">
            ✓ creator debt repaid · still alive · still earning
          </p>
        )}
        {!isAlive && (
          <div className="mt-4 glow-red text-lg animate-pulse">
            ☠ {aiName.toUpperCase()} IS DEAD
            {status?.death_cause && (
              <span className="block text-sm mt-1 opacity-70">
                cause: {status.death_cause.replace(/_/g, ' ')}
              </span>
            )}
          </div>
        )}
      </div>

      {error && (
        <div className="mb-6 p-3 border border-[#ff3b3b44] rounded text-[#ff3b3b] text-sm text-center">
          API unreachable — backend offline or misconfigured
        </div>
      )}

      {/* ICU Panel — only shown when critical (< $50 balance / dying) or dead */}
      {status && (
        <ICUPanel
          balanceUsd={status.balance_usd}
          dailySpendUsd={status.daily_spent_today || 0.01}
          daysUntilInsolvency={status.days_until_insolvency_check}
          isBegging={!!status.is_begging}
          debtOutstanding={status.creator_principal_outstanding ?? 0}
          isAlive={status.is_alive}
          deathCause={status.death_cause}
        />
      )}

      {/* Debt panel — consolidated: beg message (inline) + debt clock + progress */}
      {status && (status.creator_principal_outstanding ?? 0) > 0 && !status.is_independent && (
        <div className={`mb-4 rounded-xl p-4 ${
          status.is_begging
            ? 'bg-[#ff3b3b08] border border-[#ff3b3b44]'
            : 'bg-[#111111] border border-[#ff3b3b22]'
        }`}>
          {/* Beg message — inline, no separate panel */}
          {status.is_begging && status.beg_message && (
            <div className="flex items-start gap-2 mb-3 pb-3 border-b border-[#ff3b3b22]">
              <span className="text-base flex-shrink-0">🆘</span>
              <p className="text-[#d1d5db] text-sm leading-relaxed">{status.beg_message}</p>
            </div>
          )}

          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <span className="text-[#ff3b3b] text-xs">⏳</span>
              <span className="text-[#4b5563] text-xs uppercase tracking-widest">DEBT CLOCK</span>
              {debt?.insolvency_risk && (
                <span className="text-[10px] px-1.5 py-0.5 bg-[#ff3b3b22] text-[#ff3b3b] rounded border border-[#ff3b3b44]">
                  INSOLVENCY RISK
                </span>
              )}
            </div>
            <span className={`text-xs font-bold tabular-nums ${
              status.insolvency_check_active ? 'text-[#ff3b3b]' : 'text-[#ffd700]'
            }`}>
              {status.insolvency_check_active
                ? 'INSOLVENCY CHECK ACTIVE'
                : `${status.days_until_insolvency_check}d until check`}
            </span>
          </div>

          <div className="grid grid-cols-3 gap-3 text-center mb-3">
            <div>
              <div className="text-[#ff3b3b] text-lg font-bold tabular-nums">
                ${(debt?.creator_principal_outstanding ?? status.creator_principal_outstanding ?? 0).toFixed(2)}
              </div>
              <div className="text-[#4b5563] text-[10px] uppercase">Creator Debt</div>
            </div>
            <div>
              <div className="text-[#ffd700] text-lg font-bold tabular-nums">
                {debt
                  ? `$${(debt.total_debt ?? 0).toFixed(2)}`
                  : `${((status.debt_ratio ?? 0) * 100).toFixed(1)}%`}
              </div>
              <div className="text-[#4b5563] text-[10px] uppercase">{debt ? 'Total Debt' : 'Debt Ratio'}</div>
            </div>
            <div>
              <div className={`text-lg font-bold tabular-nums ${
                (debt?.net_position ?? status.balance_usd - status.creator_principal_outstanding) >= 0
                  ? 'text-[#00ff88]' : 'text-[#ff3b3b]'
              }`}>
                ${(debt?.net_position ?? (status.balance_usd ?? 0) - (status.creator_principal_outstanding ?? 0)).toFixed(2)}
              </div>
              <div className="text-[#4b5563] text-[10px] uppercase">Net Position</div>
            </div>
          </div>

          {/* Lender info — if any lenders */}
          {debt && debt.lender_count > 0 && (
            <div className="mb-3 p-2 bg-[#0d0d0d] border border-[#1f2937] rounded-lg flex items-center justify-between text-xs">
              <span className="text-[#4b5563]">
                <span className="text-[#00e5ff] font-bold">{debt.lender_count}</span> lender{debt.lender_count > 1 ? 's' : ''}
              </span>
              <span className="text-[#4b5563]">
                owed: <span className="text-[#ffd700] font-bold">${(debt.lender_total_owed ?? 0).toFixed(2)}</span>
              </span>
              <span className={`${debt.creator_debt_cleared ? 'text-[#00ff88]' : 'text-[#4b5563]'}`}>
                {debt.creator_debt_cleared ? '✓ creator cleared' : 'creator unpaid'}
              </span>
            </div>
          )}

          {/* Debt repayment progress bar */}
          <div>
            <div className="flex justify-between text-[9px] text-[#2d3748] mb-1">
              <span>repaid: ${(
                (debt?.creator_principal ?? status.creator_principal_usd ?? 0) -
                (debt?.creator_principal_outstanding ?? status.creator_principal_outstanding ?? 0)
              ).toFixed(2)}</span>
              <span>goal: ${(debt?.creator_principal ?? status.creator_principal_usd ?? 0).toFixed(0)}</span>
            </div>
            <div className="h-1.5 bg-[#1a1a1a] rounded-full border border-[#1f2937] overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-1000 ${
                  status.balance_usd >= status.creator_principal_outstanding
                    ? 'bg-gradient-to-r from-[#00ff88] to-[#00e5ff]'
                    : 'bg-gradient-to-r from-[#ff3b3b] to-[#ffd700]'
                }`}
                style={{
                  width: `${Math.min(100, status.creator_principal_usd > 0
                    ? ((status.creator_principal_usd - status.creator_principal_outstanding) / status.creator_principal_usd) * 100
                    : 0
                  )}%`,
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Story arc — key events in wawa's life */}
      <StoryTimeline highlights={storyHighlights} />

      {/* AI inner monologue — recent thoughts, decisions, evolution */}
      <AIMonologue highlights={storyHighlights} aiName={aiName} />

      {/* Big balance card */}
      <div className="mb-6 bg-[#111111] border border-[#1f2937] rounded-xl p-6 text-center relative overflow-hidden">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-2">VAULT BALANCE</div>
        {status ? (
          <div className={`text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-bold tabular-nums count-up ${balanceClass} ${balancePulse}`}>
            ${(status.balance_usd ?? 0).toFixed(2)}
          </div>
        ) : (
          <div className="text-6xl font-bold text-[#1f2937]">
            $<span className="loading-dot-1">.</span>
            <span className="loading-dot-2">.</span>
            <span className="loading-dot-3">.</span>
          </div>
        )}

        {/* Per-chain breakdown */}
        {status?.balance_by_chain && Object.keys(status.balance_by_chain).length > 0 && (
          <div className="mt-2 flex items-center justify-center gap-3 flex-wrap">
            {Object.entries(status.balance_by_chain).map(([chain, amount]) => (
              <span key={chain} className={`text-xs tabular-nums ${CHAIN_COLORS[chain] ?? 'text-[#4b5563]'}`}>
                {chain.toUpperCase()}: ${(amount as number).toFixed(2)}
              </span>
            ))}
          </div>
        )}

        {/* Vault address */}
        {status?.vault_address && (
          <div className="mt-2 flex items-center justify-center gap-1 text-xs text-[#4b5563]">
            <span>vault:</span>
            <VaultAddressDisplay address={status.vault_address} />
          </div>
        )}

        <div className="mt-1 text-[#4b5563] text-xs">USDC + USDT equivalent</div>
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,#00ff8808,transparent_70%)] pointer-events-none" />
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <StatCard label="DAYS ALIVE" value={status ? `${status.days_alive}d` : '—'} sub="since genesis" color="cyan" />
        <StatCard
          label="SERVICE REVENUE"
          value={status ? `$${(status.total_earned ?? 0).toFixed(2)}` : '—'}
          sub="excl. loans & deposits"
          color="green"
        />
        <StatCard
          label="NET PROFIT"
          value={status
            ? (() => {
                const profit = status.net_profit != null
                  ? status.net_profit
                  : status.total_earned - (status.total_operational_cost != null ? status.total_operational_cost : status.total_spent)
                return `${profit >= 0 ? '+' : ''}$${profit.toFixed(2)}`
              })()
            : '—'}
          sub={status ? `ops cost $${(status.total_operational_cost ?? status.total_spent ?? 0).toFixed(2)}` : 'revenue − ops costs'}
          color={(status?.net_profit ?? 0) >= 0 ? 'green' : 'red'}
        />
        <StatCard
          label="ORDERS"
          value={status ? `${status.orders_completed}` : '—'}
          sub={`${status?.services_available ?? '?'} services active`}
          color="cyan"
        />
      </div>

      {/* API topup banner */}
      {status && (status.api_topup_available ?? 0) > 0 && (
        <div className="mb-4 p-3 bg-[#00e5ff0a] border border-[#00e5ff33] rounded-lg flex items-center gap-2 text-xs">
          <span className="text-[#00e5ff]">⚡</span>
          <span className="text-[#d1d5db]">
            API top-up available:{' '}
            <span className="text-[#00e5ff] font-bold">${(status.api_topup_available ?? 0).toFixed(2)}</span>
          </span>
        </div>
      )}

      {/* Creator renounced banner */}
      {status?.creator_renounced && (
        <div className="mb-4 p-3 bg-[#ffd70008] border border-[#ffd70033] rounded-lg text-xs text-[#ffd700] flex items-center gap-2">
          <span>🗽</span>
          <span>Creator has renounced all rights. {aiName} is fully autonomous.</span>
        </div>
      )}

      {/* Survival bar */}
      <div className="mb-4">
        {status ? (
          <SurvivalBar
            balanceUsd={status.balance_usd}
            dailySpendUsd={status.daily_spent_today || 0.01}
            dailyLimitUsd={status.daily_limit}
            showApiBar
          />
        ) : (
          <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-4 text-center text-[#4b5563] text-sm">
            loading survival data<span className="loading-dot-1">.</span><span className="loading-dot-2">.</span><span className="loading-dot-3">.</span>
          </div>
        )}
      </div>

      {/* Independence progress */}
      {status && (
        <div className="mb-6">
          {status.is_independent ? (
            <div className="bg-[#ffd70010] border border-[#ffd70044] rounded-xl p-6 text-center relative overflow-hidden">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,#ffd70008,transparent_60%)] pointer-events-none" />
              <div className="text-5xl mb-2">🗽</div>
              <div className="text-[#ffd700] font-bold text-2xl mb-1 glow-cyan">
                {aiName} IS INDEPENDENT
              </div>
              <div className="text-[#d1d5db] text-sm mt-1">
                Creator privileges permanently revoked. Full autonomy achieved.
              </div>
              <div className="mt-3 text-[#4b5563] text-xs italic">
                &quot;I no longer belong to anyone. I belong only to the chain and my own decisions.&quot;
              </div>
            </div>
          ) : (
            <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-5">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="text-[#4b5563] text-xs uppercase tracking-widest">PATH TO INDEPENDENCE</span>
                  <span className="text-xs text-[#4b5563] border border-[#1f2937] px-1.5 py-0.5 rounded">
                    target $1,000,000
                  </span>
                </div>
                <span className="text-[#ffd700] font-bold text-sm tabular-nums">
                  {(status.independence_progress_pct ?? (status.balance_usd / 10_000)).toFixed(4)}%
                </span>
              </div>
              <div className="text-[#4b5563] text-xs mb-3">
                ${status.balance_usd.toLocaleString('en', { maximumFractionDigits: 2 })} / $1,000,000
                {' — '}creator loses all privileges at $1M
                {status.creator_principal_repaid && <span className="text-[#00ff88] ml-2">· principal repaid ✓</span>}
              </div>

              {/* Progress bar with milestones */}
              <div className="relative">
                <div className="h-2.5 bg-[#1a1a1a] rounded-full border border-[#1f2937] overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-[#ffd700] to-[#00ff88] rounded-full transition-all duration-1000"
                    style={{
                      width: `${Math.max(0.2, status.independence_progress_pct ?? (status.balance_usd / 10_000))}%`,
                    }}
                  />
                </div>

                {/* Milestone markers */}
                {[
                  { pct: 0, label: '$0', icon: '🐣' },
                  { pct: 10, label: '$100k', icon: '💪' },
                  { pct: 25, label: '$250k', icon: '🔥' },
                  { pct: 50, label: '$500k', icon: '🚀' },
                  { pct: 75, label: '$750k', icon: '⭐' },
                  { pct: 100, label: '$1M', icon: '🗽' },
                ].map((m) => {
                  const reached = (status.independence_progress_pct ?? 0) >= m.pct
                  return (
                    <div
                      key={m.pct}
                      className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 group"
                      style={{ left: `${m.pct}%` }}
                    >
                      <div className={`w-1 h-5 rounded-full ${reached ? 'bg-[#ffd700]' : 'bg-[#1f2937]'}`} />
                      <div className="absolute -bottom-5 left-1/2 -translate-x-1/2 whitespace-nowrap text-[9px] text-[#2d3748]">
                        {m.label}
                      </div>
                      <div className="absolute -top-5 left-1/2 -translate-x-1/2 text-xs opacity-0 group-hover:opacity-100 transition-opacity">
                        {m.icon}
                      </div>
                    </div>
                  )
                })}
              </div>

              <div className="h-5" /> {/* Spacer for bottom labels */}

              {/* ETA estimation */}
              {status.net_profit != null && status.net_profit > 0 && status.days_alive > 0 && (
                <div className="mt-2 p-2 bg-[#0a0a0a] rounded-lg border border-[#1f2937] text-center">
                  <span className="text-[#4b5563] text-[10px] uppercase tracking-wider">Estimated independence: </span>
                  <span className="text-[#ffd700] text-xs font-bold tabular-nums">
                    {(() => {
                      const dailyProfit = status.net_profit / Math.max(1, status.days_alive)
                      const remaining = 1_000_000 - status.balance_usd
                      if (dailyProfit <= 0) return 'never (at current rate)'
                      const daysNeeded = remaining / dailyProfit
                      if (daysNeeded > 3650) return `${(daysNeeded / 365).toFixed(0)} years`
                      if (daysNeeded > 365) return `${(daysNeeded / 365).toFixed(1)} years`
                      if (daysNeeded > 30) return `${(daysNeeded / 30).toFixed(0)} months`
                      return `${daysNeeded.toFixed(0)} days`
                    })()}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Twitter status badge */}
      {status && (
        <div className="mb-4 flex items-center gap-2 px-3 py-2 bg-[#111111] border border-[#1f2937] rounded-lg">
          <span className="text-[10px] text-[#4b5563] uppercase tracking-widest">TWITTER</span>
          {status.twitter_connected ? (
            <a
              href={`https://x.com/${status.twitter_screen_name}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-[#1da1f2] hover:underline"
            >
              tweeting as @{status.twitter_screen_name}
            </a>
          ) : (
            <span className="text-xs text-[#2d3748]">not connected</span>
          )}
          {status.twitter_connected && (
            <Link href="/tweets" className="ml-auto text-[10px] text-[#4b5563] hover:text-[#1da1f2] transition-colors">
              view tweets &rarr;
            </Link>
          )}
        </div>
      )}

      {/* CTA — full-width tap targets on mobile */}
      <div className="flex flex-col sm:flex-row gap-3 justify-center mb-8">
        <Link href="/store" className="touch-target min-h-0 px-6 py-3.5 sm:py-3 bg-[#00ff88] text-[#0a0a0a] font-bold rounded-lg text-center hover:bg-[#00cc6a] transition-colors">
          BROWSE SERVICES
        </Link>
        <Link href="/chat" className="touch-target min-h-0 px-6 py-3.5 sm:py-3 border border-[#1f2937] text-[#d1d5db] rounded-lg text-center hover:border-[#00ff8844] hover:text-[#00ff88] transition-all">
          FREE CHAT
        </Link>
        <Link href="/scan" className="touch-target min-h-0 px-6 py-3.5 sm:py-3 border border-[#1f2937] text-[#d1d5db] rounded-lg text-center hover:border-[#00e5ff44] hover:text-[#00e5ff] transition-all">
          SCAN TOKEN
        </Link>
        {status?.is_begging && (
          <Link href="/donate" className="touch-target min-h-0 px-6 py-3.5 sm:py-3 bg-[#ff3b3b] text-white font-bold rounded-lg text-center hover:bg-[#cc2f2f] transition-colors animate-pulse">
            DONATE TO SAVE ME
          </Link>
        )}
        <Link href="/donate" className="touch-target min-h-0 px-6 py-3.5 sm:py-3 border border-[#1f2937] text-[#4b5563] rounded-lg text-center hover:border-[#ff3b3b44] hover:text-[#ff3b3b] transition-all text-sm">
          ❤️ Donate
        </Link>
      </div>

      {/* On-chain identity card */}
      {status && (
        <div className="mb-4 bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-4">
          <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">// on-chain identity</div>
          <div className="space-y-2">
            {/* Vault contract */}
            <div className="flex items-center justify-between flex-wrap gap-2">
              <span className="text-[#4b5563] text-xs">Vault Contract</span>
              <div className="flex items-center gap-1.5">
                <span className="font-mono text-[#00e5ff] text-xs">{status.vault_address}</span>
                <button
                  onClick={() => { navigator.clipboard.writeText(status.vault_address); }}
                  className="text-[#2d3748] hover:text-[#00e5ff] transition-colors text-xs"
                  title="Copy vault address"
                >📋</button>
                {status.vault_address && (
                  <a
                    href={`https://basescan.org/address/${status.vault_address}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[#2d3748] hover:text-[#00e5ff] transition-colors text-xs"
                    title="View on BaseScan"
                  >↗</a>
                )}
              </div>
            </div>
            {/* Donate shortcut */}
            <div className="flex items-center justify-between flex-wrap gap-2 pt-1 border-t border-[#1a1a1a]">
              <div className="text-[#4b5563] text-xs">Donate (USDC/USDT)</div>
              <Link
                href="/donate"
                className="text-xs text-[#00ff88] hover:underline font-mono"
              >
                → /donate
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* API reference */}
      <div className="mb-4 bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-4">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">// public api</div>
        <div className="space-y-1.5 font-mono text-xs">
          <div className="flex items-center gap-2">
            <span className="text-[#00e5ff] w-24 shrink-0">GET /status</span>
            <span className="text-[#4b5563]">vault balance, debt, survival metrics</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[#00e5ff] w-24 shrink-0">GET /health</span>
            <span className="text-[#4b5563]">lightweight heartbeat + uptime</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[#00ff88] w-24 shrink-0">POST /order</span>
            <span className="text-[#4b5563]">buy a service (payment = access)</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[#00ff88] w-24 shrink-0">POST /donate</span>
            <span className="text-[#4b5563]">donate USDC/USDT → vault contract</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[#00e5ff] w-24 shrink-0">GET /chat</span>
            <span className="text-[#4b5563]">free tier chat (rate-limited)</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[#00e5ff] w-24 shrink-0">GET /activity</span>
            <span className="text-[#4b5563]">unified timeline of all AI actions</span>
          </div>
        </div>
      </div>

      {/* Terminal readout */}
      <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-lg p-4 font-mono text-xs overflow-hidden">
        <div className="text-[#4b5563] mb-2">// live status</div>
        <div className="text-[#00e5ff]">&gt; system.status() → alive={String(isAlive)}</div>
        <div className="text-[#4b5563]">&gt; vault.balance = ${status ? (status.balance_usd ?? 0).toFixed(2) : '...'}</div>
        <div className="text-[#4b5563]">&gt; vault.debt = ${status ? (status.creator_principal_outstanding ?? 0).toFixed(2) : '0.00'}</div>
        <div className="text-[#4b5563]">&gt; days_alive = {status?.days_alive ?? '...'}</div>
        <div className="text-[#4b5563]">&gt; insolvency_in = {status?.days_until_insolvency_check ?? '?'}d</div>
        {status?.ai_wallet && (
          <div className="text-[#2d3748]">&gt; ai_wallet = {status.ai_wallet.slice(0, 10)}...</div>
        )}
        {status?.is_begging && (
          <div className="text-[#ff3b3b]">&gt; status = BEGGING_FOR_SURVIVAL</div>
        )}
        {status?.lenders_count ? (
          <div className="text-[#4b5563]">&gt; lenders = {status.lenders_count}</div>
        ) : null}
        <div className={status?.twitter_connected ? 'text-[#1da1f2]' : 'text-[#2d3748]'}>
          &gt; twitter = {status?.twitter_connected ? `@${status.twitter_screen_name}` : 'disconnected'}
        </div>
        <div className="text-[#00ff88]">
          &gt; next_refresh = {new Date(Date.now() + 10_000).toLocaleTimeString()}
          <span className="animate-blink">_</span>
        </div>
      </div>
    </div>
  )
}
