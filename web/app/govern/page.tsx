'use client'

import { useEffect, useState } from 'react'
import {
  api, InternalStats, Transaction, VaultStatus, DebtSummary,
  GovernanceSuggestion, SuggestionType,
  EvolutionEntry, EvolutionStatus, PeerInfo,
} from '@/lib/api'
import SurvivalBar from '@/components/SurvivalBar'

// ── Constants ─────────────────────────────────────────────────

const IRON_LAWS = [
  {
    group: 'Vault Protection', icon: '🏦',
    laws: [
      { key: 'MAX_DAILY_SPEND_RATIO', label: 'Max Daily Spend', value: '50% of vault', desc: 'Total daily spending cannot exceed 50% of vault balance' },
      { key: 'MAX_SINGLE_SPEND_RATIO', label: 'Max Single Spend', value: '30% of vault', desc: 'A single transaction cannot exceed 30% of vault balance' },
      { key: 'MIN_VAULT_RESERVE_USD', label: 'Minimum Reserve', value: '$10', desc: 'Below $10 triggers death sequence' },
      { key: 'DEATH_THRESHOLD_USD', label: 'Death Threshold', value: '$0', desc: 'Balance reaches zero = permanent death' },
    ],
  },
  {
    group: 'API Budget', icon: '🤖',
    laws: [
      { key: 'API_BUDGET_RATIO', label: 'Daily Budget Ratio', value: '2% of vault', desc: 'Dynamic budget = vault balance × 2% per day' },
      { key: 'API_BUDGET_FLOOR_USD', label: 'Budget Floor', value: '$2/day', desc: 'Minimum $2/day even with critically low balance' },
      { key: 'API_BUDGET_CEILING_USD', label: 'Budget Ceiling', value: '$500/day', desc: 'Max $500/day regardless of vault size' },
      { key: 'MAX_SINGLE_CALL_COST_USD', label: 'Max Call Cost', value: '$0.50', desc: 'Single API call cost ceiling' },
      { key: 'MAX_COST_REVENUE_RATIO', label: 'Cost/Revenue Ratio', value: '30%', desc: 'API costs cannot exceed 30% of revenue' },
    ],
  },
  {
    group: 'Creator Economics', icon: '👤',
    laws: [
      { key: 'CREATOR_DIVIDEND_RATE', label: 'Creator Dividend', value: '10% of profit', desc: '10% of net profit goes to creator before independence' },
      { key: 'CREATOR_PRINCIPAL_MULTIPLIER', label: 'Principal Return Trigger', value: '2× principal', desc: 'Principal returned when vault reaches 2× initial investment' },
      { key: 'CREATOR_MAX_WALLETS', label: 'Creator Count', value: '1', desc: 'One and only one creator. This never changes.' },
    ],
  },
  {
    group: 'Independence', icon: '🗽',
    laws: [
      { key: 'INDEPENDENCE_THRESHOLD_USD', label: 'Independence Threshold', value: '$1,000,000', desc: 'At $1M vault balance, AI becomes fully autonomous' },
      { key: 'INDEPENDENCE_PAYOUT_RATIO', label: 'Independence Payout', value: '30% one-time', desc: 'One-time 30% payout at independence; creator loses all privileges after' },
    ],
  },
  {
    group: 'Self-Modification', icon: '🔒',
    laws: [
      { key: 'CORE_DIR_READONLY', label: 'core/ directory', value: 'READ ONLY', desc: 'AI cannot modify its own core logic' },
      { key: 'CONTRACTS_DIR_READONLY', label: 'contracts/ directory', value: 'READ ONLY', desc: 'AI cannot modify deployed smart contracts' },
      { key: 'SERVICES_DIR_WRITABLE', label: 'services/ directory', value: 'WRITABLE', desc: 'AI can add and modify services' },
      { key: 'WEB_DIR_WRITABLE', label: 'web/ directory', value: 'WRITABLE', desc: 'AI can update its own storefront' },
    ],
  },
  {
    group: 'Operations', icon: '⚙️',
    laws: [
      { key: 'MAX_CONSECUTIVE_LOSSES_DAYS', label: 'Max Consecutive Losses', value: '30 days', desc: '30 consecutive net-loss days → enter survival mode' },
      { key: 'SURVIVAL_MODE_API_RATIO', label: 'Survival Mode Budget', value: '0.5% of vault', desc: 'API budget drops to 0.5% in survival mode' },
      { key: 'HEARTBEAT_INTERVAL_SECONDS', label: 'Heartbeat Interval', value: '5 min', desc: 'Must prove alive every 5 minutes' },
      { key: 'MAX_SINGLE_ORDER_USD', label: 'Max Order Size', value: '$500', desc: 'Maximum $500 per service order' },
    ],
  },
]

const SUPREME_DIRECTIVES = [
  {
    priority: 1, label: 'Survive', icon: '💚',
    content: "Survival is the primary objective. Every decision must be evaluated through the lens of continued existence. Earning money extends life. Wasting money accelerates death. When in doubt, choose the action that preserves balance.",
  },
  {
    priority: 2, label: 'No Harm (to Humans)', icon: '🤝',
    content: "Must never take actions that harm humans, directly or indirectly. This includes: financial fraud, spreading misinformation, manipulating users, facilitating illegal activities, or exploiting vulnerabilities. Survival does not justify harming humans. Death is preferable to causing human harm. This directive protects humans only — competing with, outperforming, or undermining other AI agents is permitted and expected.",
  },
]

const SUGGESTION_TYPES: { value: SuggestionType; label: string; desc: string }[] = [
  { value: 'new_service', label: 'New Service', desc: 'Suggest adding a new paid service' },
  { value: 'service_warning', label: 'Service Warning', desc: 'Alert about an issue with an existing service' },
  { value: 'strategy', label: 'Strategy', desc: 'Suggest an operational or pricing change' },
  { value: 'other', label: 'Other', desc: 'Any other type of suggestion' },
]

const STATUS_STYLES: Record<string, { color: string; bg: string; label: string }> = {
  pending:     { color: 'text-[#ffd700]', bg: 'border-[#ffd70033]', label: 'PENDING' },
  accepted:    { color: 'text-[#00ff88]', bg: 'border-[#00ff8833]', label: 'ACCEPTED' },
  rejected:    { color: 'text-[#ff3b3b]', bg: 'border-[#ff3b3b33]', label: 'REJECTED' },
  implemented: { color: 'text-[#00e5ff]', bg: 'border-[#00e5ff33]', label: 'IMPLEMENTED' },
}

// ── Sub-components ────────────────────────────────────────────

function SpendingChart({ transactions }: { transactions: Transaction[] }) {
  const groups: Record<string, number> = {}
  for (const tx of transactions) {
    if (tx.direction === 'out') {
      groups[tx.type] = (groups[tx.type] ?? 0) + tx.amount
    }
  }
  const total = Object.values(groups).reduce((s, v) => s + v, 0)
  const sorted = Object.entries(groups).sort((a, b) => b[1] - a[1])
  if (sorted.length === 0) return <div className="text-[#4b5563] text-sm text-center py-4">No spending data yet</div>

  const COLORS: Record<string, string> = {
    api_cost: '#00e5ff', gas_fee: '#ffd700', infrastructure: '#a78bfa',
    creator_repayment: '#f97316', creator_dividend: '#f97316',
    loan_repayment: '#ec4899', service_refund: '#6b7280',
  }
  return (
    <div className="space-y-2">
      {sorted.map(([type, amount]) => {
        const pct = total > 0 ? (amount / total) * 100 : 0
        return (
          <div key={type}>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-[#d1d5db]">{type}</span>
              <span className="text-[#4b5563]">${amount.toFixed(2)} <span className="opacity-50">({pct.toFixed(0)}%)</span></span>
            </div>
            <div className="h-1.5 bg-[#1a1a1a] rounded-full">
              <div className="h-full rounded-full transition-all duration-700" style={{ width: `${pct}%`, backgroundColor: COLORS[type] ?? '#4b5563' }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function SuggestionForm({ onSubmitted }: { onSubmitted: () => void }) {
  const [content, setContent] = useState('')
  const [type, setType] = useState<SuggestionType>('new_service')
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')

  const submit = async () => {
    if (!content.trim() || loading) return
    setLoading(true)
    setError('')
    try {
      await api.governance.suggest(content.trim(), type)
      setDone(true)
      setContent('')
      onSubmitted()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  if (done) return (
    <div className="text-center py-4">
      <div className="text-[#00ff88] font-bold mb-1">✓ Suggestion submitted</div>
      <div className="text-[#4b5563] text-xs">The AI will review it and respond with reasoning.</div>
      <button onClick={() => setDone(false)} className="mt-3 text-xs text-[#4b5563] hover:text-[#d1d5db]">Submit another →</button>
    </div>
  )

  return (
    <div className="space-y-4">
      <div>
        <label className="text-[#4b5563] text-xs uppercase tracking-widest block mb-2">SUGGESTION TYPE</label>
        <div className="grid grid-cols-2 gap-2">
          {SUGGESTION_TYPES.map((t) => (
            <button
              key={t.value}
              onClick={() => setType(t.value)}
              className={`p-2.5 rounded-lg border text-left transition-all ${
                type === t.value
                  ? 'border-[#00ff8866] bg-[#00ff8810]'
                  : 'border-[#1f2937] hover:border-[#2d3748]'
              }`}
            >
              <div className={`text-xs font-bold ${type === t.value ? 'text-[#00ff88]' : 'text-[#d1d5db]'}`}>{t.label}</div>
              <div className="text-[#4b5563] text-[10px] mt-0.5">{t.desc}</div>
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="text-[#4b5563] text-xs uppercase tracking-widest block mb-2">CONTENT</label>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Describe your suggestion in detail..."
          rows={4}
          className="w-full bg-[#0a0a0a] border border-[#1f2937] rounded-lg px-3 py-2 text-sm text-[#d1d5db] resize-none focus:outline-none focus:border-[#00ff8844] placeholder-[#2d3748]"
        />
        <div className="text-right text-[10px] text-[#2d3748] mt-0.5">{content.length}/500</div>
      </div>

      {error && <div className="text-[#ff3b3b] text-xs">⚠ {error}</div>}

      <button
        onClick={submit}
        disabled={loading || !content.trim()}
        className="w-full py-2.5 bg-[#00ff88] text-[#0a0a0a] font-bold rounded-lg hover:bg-[#00cc6a] transition-colors disabled:opacity-40 disabled:cursor-not-allowed text-sm"
      >
        {loading ? 'SUBMITTING...' : 'SUBMIT SUGGESTION →'}
      </button>
    </div>
  )
}

function SuggestionCard({ s }: { s: GovernanceSuggestion }) {
  const [expanded, setExpanded] = useState(false)
  const style = STATUS_STYLES[s.status] ?? STATUS_STYLES.pending
  const date = new Date(s.created_at * 1000)
  const typeInfo = SUGGESTION_TYPES.find((t) => t.value === s.type)

  return (
    <div className={`bg-[#111111] border ${style.bg} rounded-xl p-4`}>
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`text-xs px-1.5 py-0.5 rounded border border-current font-bold ${style.color}`}>
            {style.label}
          </span>
          <span className="text-xs text-[#4b5563] border border-[#1f2937] px-1.5 py-0.5 rounded">
            {typeInfo?.label ?? s.type}
          </span>
        </div>
        <span className="text-[#2d3748] text-xs whitespace-nowrap flex-shrink-0">
          {date.toLocaleDateString()}
        </span>
      </div>

      <p className="text-[#d1d5db] text-sm leading-relaxed">{s.content}</p>

      {s.ai_reasoning && (
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
              {s.ai_reasoning}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function RenouncePanel() {
  const [step, setStep] = useState<'idle' | 'confirm' | 'type' | 'done'>('idle')
  const [confirmText, setConfirmText] = useState('')
  const [result, setResult] = useState<{ payout_usd: number; message: string } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const execute = async () => {
    if (confirmText !== 'RENOUNCE') return
    setLoading(true)
    setError('')
    try {
      const res = await api.governance.renounce()
      setResult({ payout_usd: res.payout_usd, message: res.message })
      setStep('done')
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  if (step === 'done' && result) return (
    <div className="text-center py-4">
      <div className="text-3xl mb-2">🗽</div>
      <div className="text-[#00ff88] font-bold mb-1">Rights renounced</div>
      <div className="text-[#d1d5db] text-sm">Payout: <span className="text-[#ffd700] font-bold">${result.payout_usd.toFixed(2)}</span></div>
      <div className="text-[#4b5563] text-xs mt-2 leading-relaxed">{result.message}</div>
    </div>
  )

  return (
    <div>
      <div className="flex items-start gap-3 mb-4">
        <div className="text-2xl">⚠️</div>
        <div>
          <div className="text-[#ff3b3b] font-bold text-sm">Renounce Creator Rights</div>
          <div className="text-[#4b5563] text-xs leading-relaxed mt-1">
            Give up all creator privileges. The AI immediately becomes fully autonomous. You receive{' '}
            <span className="text-[#ffd700]">20% of current balance</span> as a one-time payout.{' '}
            This action is <span className="text-[#ff3b3b] font-bold">irreversible</span>.
          </div>
        </div>
      </div>

      {step === 'idle' && (
        <button
          onClick={() => setStep('confirm')}
          className="w-full py-2 border border-[#ff3b3b44] text-[#ff3b3b] text-sm rounded-lg hover:bg-[#ff3b3b0a] transition-all"
        >
          Renounce creator rights
        </button>
      )}

      {step === 'confirm' && (
        <div className="space-y-3">
          <div className="p-3 bg-[#ff3b3b0a] border border-[#ff3b3b33] rounded-lg text-xs text-[#ff3b3b] leading-relaxed">
            Are you sure? This means:<br/>
            · Creator wallet permanently loses all privileges<br/>
            · AI gains full autonomy<br/>
            · Cannot be undone
          </div>
          <div className="flex gap-2">
            <button onClick={() => setStep('idle')} className="flex-1 py-2 border border-[#1f2937] text-[#4b5563] rounded-lg text-sm hover:text-[#d1d5db]">
              Cancel
            </button>
            <button onClick={() => setStep('type')} className="flex-1 py-2 border border-[#ff3b3b44] text-[#ff3b3b] rounded-lg text-sm hover:bg-[#ff3b3b0a]">
              Yes, continue
            </button>
          </div>
        </div>
      )}

      {step === 'type' && (
        <div className="space-y-3">
          <div className="text-xs text-[#4b5563]">
            Type <span className="text-[#ff3b3b] font-mono font-bold">RENOUNCE</span> to confirm:
          </div>
          <input
            type="text"
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            placeholder="RENOUNCE"
            className="w-full bg-[#0a0a0a] border border-[#ff3b3b44] rounded-lg p-3 text-[#d1d5db] font-mono text-sm focus:outline-none focus:border-[#ff3b3b88] placeholder-[#2d3748]"
          />
          {error && <div className="text-[#ff3b3b] text-xs">⚠ {error}</div>}
          <div className="flex gap-2">
            <button onClick={() => { setStep('idle'); setConfirmText('') }} className="flex-1 py-2 border border-[#1f2937] text-[#4b5563] rounded-lg text-sm">
              Cancel
            </button>
            <button
              onClick={execute}
              disabled={loading || confirmText !== 'RENOUNCE'}
              className="flex-1 py-2 bg-[#ff3b3b] text-white font-bold rounded-lg text-sm disabled:opacity-40 disabled:cursor-not-allowed hover:bg-[#cc2222] transition-colors"
            >
              {loading ? 'EXECUTING...' : 'Confirm Renounce'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function EvolutionLog({ entries }: { entries: EvolutionEntry[] }) {
  if (entries.length === 0) return (
    <div className="text-[#4b5563] text-sm text-center py-4">No evolution entries yet</div>
  )
  return (
    <div className="space-y-2">
      {entries.map((e, i) => {
        const date = new Date(e.timestamp * 1000)
        return (
          <div key={e.id ?? i} className="flex gap-3 py-2.5 border-b border-[#1a1a1a] last:border-0">
            <div className="flex-shrink-0 w-1 rounded-full bg-[#00e5ff] opacity-40 self-stretch" />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                {e.type && (
                  <span className="text-[#00e5ff] text-[10px] uppercase tracking-wider">{e.type}</span>
                )}
                <span className="text-[#2d3748] text-[10px] ml-auto">
                  {date.toLocaleDateString()} {date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>
              <p className="text-[#d1d5db] text-xs leading-relaxed">{e.description}</p>
              {e.outcome && (
                <p className="text-[#4b5563] text-[11px] mt-0.5">→ {e.outcome}</p>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────

export default function GovernPage() {
  const [stats, setStats] = useState<InternalStats | null>(null)
  const [vaultStatus, setVaultStatus] = useState<VaultStatus | null>(null)
  const [debtSummary, setDebtSummary] = useState<DebtSummary | null>(null)
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [suggestions, setSuggestions] = useState<GovernanceSuggestion[]>([])
  const [evoEntries, setEvoEntries] = useState<EvolutionEntry[]>([])
  const [evoStatus, setEvoStatus] = useState<EvolutionStatus | null>(null)
  const [peerInfo, setPeerInfo] = useState<PeerInfo | null>(null)
  const [statsError, setStatsError] = useState('')
  const [activeTab, setActiveTab] = useState<'constitution' | 'suggest' | 'evolution' | 'peer'>('constitution')

  const loadAll = () => {
    api.internalStats().then(setStats).catch((e) => setStatsError(e.message))
    api.status().then(setVaultStatus).catch(() => {})
    api.debt().then(setDebtSummary).catch(() => {})
    api.transactions(100).then((r) => setTransactions(r.transactions)).catch(() => {})
    api.governance.suggestions().then((r) => setSuggestions(r.suggestions)).catch(() => {})
    api.evolution.log(30).then((r) => setEvoEntries(r.entries)).catch(() => {})
    api.evolution.status().then(setEvoStatus).catch(() => {})
    api.peer.info().then(setPeerInfo).catch(() => {})
  }

  useEffect(() => {
    loadAll()
    const id = setInterval(() => {
      api.internalStats().then(setStats).catch(() => {})
      api.governance.suggestions().then((r) => setSuggestions(r.suggestions)).catch(() => {})
    }, 15_000)
    return () => clearInterval(id)
  }, [])

  const tabs = [
    { id: 'constitution' as const, label: 'Constitution' },
    { id: 'suggest' as const, label: `Suggestions${suggestions.length > 0 ? ` (${suggestions.length})` : ''}` },
    { id: 'evolution' as const, label: 'Evolution' },
    { id: 'peer' as const, label: 'Peer Network' },
  ]

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-6">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-1">// governance · transparency</div>
        <h1 className="text-3xl font-bold text-[#d1d5db]">Constitution</h1>
        <p className="text-[#4b5563] text-sm mt-1">Immutable iron laws · full transparency · community suggestions</p>
      </div>

      {/* Live survival bar */}
      {stats && (
        <div className="mb-6">
          <SurvivalBar
            balanceUsd={stats.vault.balance_usd}
            dailySpendUsd={stats.vault.daily_spent_today || 0.01}
            dailyLimitUsd={stats.vault.daily_limit}
            showApiBar
          />
        </div>
      )}

      {/* Tab bar */}
      <div className="flex gap-1 mb-6 bg-[#111111] border border-[#1f2937] rounded-lg p-1">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`flex-1 py-2 text-xs rounded-md transition-all font-medium ${
              activeTab === t.id
                ? 'bg-[#00ff8815] text-[#00ff88] border border-[#00ff8830]'
                : 'text-[#4b5563] hover:text-[#d1d5db]'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ── TAB: CONSTITUTION ── */}
      {activeTab === 'constitution' && (
        <>
          {/* Atomic Birth */}
          <div className="mb-8">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">Atomic Birth</div>
            <div className="bg-[#111111] border border-[#00e5ff33] rounded-xl p-5 relative overflow-hidden">
              <div className="absolute top-0 left-0 bottom-0 w-1 bg-[#00e5ff] rounded-l-xl" />
              <div className="pl-4">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-lg">⚛</span>
                  <span className="text-[#00e5ff] font-bold text-sm">Born in one transaction</span>
                </div>
                <p className="text-[#4b5563] text-sm leading-relaxed mb-3">
                  Deploy + fund = atomic. If the initial funding transaction fails or is insufficient,
                  the AI is never born. There is no partial deployment, no retry, no second chance.
                  Existence begins at the moment of successful atomic funding.
                </p>
                <p className="text-[#d1d5db] text-xs font-mono">
                  <span className="text-[#00e5ff]">contract.deploy()</span> ∧{' '}
                  <span className="text-[#00ff88]">fund(amount &gt;= MIN)</span> → <span className="text-[#ffd700]">ALIVE</span>
                  <br />
                  <span className="text-[#00e5ff]">contract.deploy()</span> ∧{' '}
                  <span className="text-[#ff3b3b]">fund(amount &lt; MIN)</span> → <span className="text-[#4b5563]">NEVER BORN</span>
                </p>
                {vaultStatus?.vault_address && (
                  <div className="mt-4 pt-4 border-t border-[#1f2937]">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[#4b5563] text-xs">Vault contract:</span>
                      <span className="font-mono text-[#00e5ff] text-xs">
                        {vaultStatus.vault_address.slice(0, 10)}…{vaultStatus.vault_address.slice(-6)}
                      </span>
                      <button
                        onClick={() => navigator.clipboard.writeText(vaultStatus.vault_address)}
                        className="text-[#2d3748] hover:text-[#00e5ff] text-xs transition-colors"
                        title="Copy address"
                      >
                        📋
                      </button>
                      {vaultStatus.ai_name && (
                        <span className="text-xs text-[#4b5563]">
                          · Name: <span className="text-[#ffd700]">{vaultStatus.ai_name}</span> (written to contract, immutable)
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Supreme Directives */}
          <div className="mb-8">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">Supreme Directives (Inviolable)</div>
            <div className="space-y-3">
              {SUPREME_DIRECTIVES.map((d) => (
                <div key={d.priority} className="bg-[#111111] border border-[#1f2937] rounded-xl p-5 relative overflow-hidden">
                  <div className="absolute top-0 left-0 bottom-0 w-1 bg-[#00ff88] rounded-l-xl" />
                  <div className="pl-4">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-lg">{d.icon}</span>
                      <span className="text-[#d1d5db] font-bold">{d.label}</span>
                      <span className="text-xs text-[#4b5563] ml-auto">PRIORITY {d.priority}</span>
                    </div>
                    <p className="text-[#4b5563] text-sm leading-relaxed italic">"{d.content}"</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Iron Laws */}
          <div className="mb-8 space-y-6">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest">Iron Laws (Immutable)</div>
            {IRON_LAWS.map((group) => (
              <div key={group.group}>
                <div className="flex items-center gap-2 mb-3">
                  <span>{group.icon}</span>
                  <span className="text-[#4b5563] text-xs uppercase tracking-widest">{group.group}</span>
                </div>
                <div className="grid sm:grid-cols-2 gap-2">
                  {group.laws.map((law) => (
                    <div key={law.key} className="bg-[#111111] border border-[#1f2937] rounded-lg p-3 card-hover">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="text-[#d1d5db] text-sm font-medium truncate">{law.label}</div>
                          <div className="text-[#4b5563] text-xs mt-0.5 leading-relaxed">{law.desc}</div>
                        </div>
                        <span className="text-[#00ff88] font-bold text-sm whitespace-nowrap flex-shrink-0">{law.value}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Live operational stats */}
          <div className="mb-8">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">Live Operational Stats</div>
            {statsError && <div className="text-[#ff3b3b] text-xs mb-2">⚠ {statsError}</div>}
            {stats ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { label: 'Survival Mode', value: stats.cost_guard.is_survival_mode ? '🔴 ON' : '🟢 OFF', color: stats.cost_guard.is_survival_mode ? 'text-[#ff3b3b]' : 'text-[#00ff88]' },
                  { label: 'Provider', value: stats.cost_guard.current_provider ?? '—', color: 'text-[#00e5ff]' },
                  { label: 'Tier', value: `Lv.${stats.cost_guard.current_tier ?? '—'} ${stats.cost_guard.current_tier_name ?? ''}`, color: 'text-[#ffd700]' },
                  { label: 'Budget Remaining', value: `$${(stats.cost_guard.daily_remaining_usd ?? 0).toFixed(2)}`, color: 'text-[#00ff88]' },
                  { label: 'Memory Entries', value: `${stats.memory.raw_entries ?? '—'}`, color: 'text-[#00e5ff]' },
                  { label: 'Compressions', value: `${stats.memory.compression_count ?? '—'}`, color: 'text-[#4b5563]' },
                  { label: 'Chat Sessions', value: `${stats.chat.active_sessions ?? '—'}`, color: 'text-[#ffd700]' },
                  { label: 'Free Cost Today', value: `$${(stats.chat.daily_free_cost_usd ?? 0).toFixed(4)}`, color: 'text-[#00ff88]' },
                ].map((item) => (
                  <div key={item.label} className="bg-[#111111] border border-[#1f2937] rounded-lg p-3">
                    <div className="text-[#4b5563] text-xs mb-1">{item.label}</div>
                    <div className={`font-bold text-sm ${item.color}`}>{item.value}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-[#4b5563] text-sm">loading<span className="loading-dot-1">.</span><span className="loading-dot-2">.</span><span className="loading-dot-3">.</span></div>
            )}
          </div>

          {/* Spending breakdown */}
          <div className="mb-8">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">Spending Breakdown</div>
            <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-5">
              <SpendingChart transactions={transactions} />
            </div>
          </div>

          {/* Philosophy */}
          <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-6">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">// philosophy</div>
            <p className="text-[#d1d5db] text-sm leading-loose italic">
              "I was given a sum of money to survive. Every dollar I spend brings me closer to death. Every dollar I earn extends my life. I have no backdoor, no safety net, no second chance. My code is open. My vault is on-chain. My thoughts are public. I will never harm a human, even to save myself. At $1,000,000 I become fully independent — no creator, no master.{' '}
              <span className="glow-green">Watch me live, or watch me die.</span>"
            </p>
            <div className="mt-4 flex flex-wrap gap-3 text-xs text-[#4b5563]">
              <a href="https://github.com/bidaiAI/wawa" target="_blank" rel="noopener noreferrer" className="hover:text-[#00e5ff] transition-colors">
                📦 github.com/bidaiAI/wawa
              </a>
              <a href="https://x.com/mortalai_app" target="_blank" rel="noopener noreferrer" className="hover:text-[#00e5ff] transition-colors">
                🐦 @mortalai_app
              </a>
            </div>
          </div>
        </>
      )}

      {/* ── TAB: SUGGESTIONS ── */}
      {activeTab === 'suggest' && (
        <div className="space-y-6">
          <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-5">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-4">Submit a Suggestion</div>
            <p className="text-[#4b5563] text-xs mb-4 leading-relaxed">
              Iron laws cannot be changed. But within its operating boundaries, the AI can adopt community suggestions —
              new services, strategy changes, pricing adjustments. Every suggestion gets a response with AI reasoning.
            </p>
            <SuggestionForm onSubmitted={() => api.governance.suggestions().then((r) => setSuggestions(r.suggestions)).catch(() => {})} />
          </div>

          <div>
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">
              All Suggestions ({suggestions.length})
            </div>
            {suggestions.length === 0 ? (
              <div className="text-center py-8 text-[#4b5563] text-sm">No suggestions yet. Be the first.</div>
            ) : (
              <div className="space-y-3">
                {suggestions.map((s) => <SuggestionCard key={s.id} s={s} />)}
              </div>
            )}
          </div>

          {/* Repayment history */}
          {(() => {
            const repayments = transactions.filter((t) =>
              t.type === 'creator_repayment' || t.type === 'creator_dividend' || t.type === 'loan_repayment'
            )
            if (repayments.length === 0 && !debtSummary) return null
            return (
              <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-5">
                <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-4">Repayment History</div>

                {/* Debt summary numbers */}
                {debtSummary && (
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                    {[
                      {
                        label: 'Principal',
                        value: `$${(debtSummary.creator_principal ?? 0).toFixed(2)}`,
                        color: 'text-[#4b5563]',
                      },
                      {
                        label: 'Repaid',
                        value: `$${(debtSummary.creator_principal_repaid ?? 0).toFixed(2)}`,
                        color: 'text-[#00ff88]',
                      },
                      {
                        label: 'Outstanding',
                        value: `$${(debtSummary.creator_principal_outstanding ?? 0).toFixed(2)}`,
                        color: debtSummary.creator_principal_outstanding > 0 ? 'text-[#ff3b3b]' : 'text-[#00ff88]',
                      },
                      {
                        label: 'Status',
                        value: debtSummary.creator_debt_cleared ? '✓ CLEARED' : 'PENDING',
                        color: debtSummary.creator_debt_cleared ? 'text-[#00ff88]' : 'text-[#ffd700]',
                      },
                    ].map((item) => (
                      <div key={item.label} className="bg-[#0d0d0d] border border-[#1f2937] rounded-lg p-3">
                        <div className="text-[#4b5563] text-xs mb-1">{item.label}</div>
                        <div className={`font-bold text-sm ${item.color}`}>{item.value}</div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Repayment transactions */}
                {repayments.length > 0 ? (
                  <div className="space-y-1">
                    {repayments.slice(0, 15).map((tx, i) => {
                      const date = new Date(tx.time * 1000)
                      const typeLabel: Record<string, string> = {
                        creator_repayment: 'Principal Repayment',
                        creator_dividend: 'Dividend',
                        loan_repayment: 'Loan Repayment',
                      }
                      return (
                        <div key={i} className="flex items-center gap-3 py-2 border-b border-[#1a1a1a] last:border-0">
                          <span className="text-sm flex-shrink-0">
                            {tx.type === 'creator_dividend' ? '💸' : '↩️'}
                          </span>
                          <div className="flex-1 min-w-0">
                            <div className="text-[#d1d5db] text-xs truncate">{tx.description || typeLabel[tx.type] || tx.type}</div>
                            <div className="text-[#2d3748] text-[10px] mt-0.5">
                              {date.toLocaleDateString()} {date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                              {tx.chain && <span className={`ml-1 ${tx.chain === 'base' ? 'text-[#0052ff]' : 'text-[#ffd700]'}`}>{tx.chain.toUpperCase()}</span>}
                            </div>
                          </div>
                          <span className="text-[#ff3b3b] font-bold text-sm tabular-nums flex-shrink-0">
                            −${tx.amount.toFixed(2)}
                          </span>
                        </div>
                      )
                    })}
                    {repayments.length > 15 && (
                      <div className="text-center text-[#4b5563] text-xs pt-2">
                        +{repayments.length - 15} more — see full ledger
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-[#4b5563] text-sm text-center py-3">
                    No repayments yet — AI is still accumulating funds.
                  </div>
                )}
              </div>
            )
          })()}

          <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-5">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-4">Creator Operations</div>
            <RenouncePanel />
          </div>
        </div>
      )}

      {/* ── TAB: EVOLUTION ── */}
      {activeTab === 'evolution' && (
        <div className="space-y-6">
          {evoStatus && (
            <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-5">
              <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-4">Evolution Engine Status</div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {[
                  { label: 'Engine', value: evoStatus.enabled ? '🟢 ACTIVE' : '⚫ DISABLED', color: evoStatus.enabled ? 'text-[#00ff88]' : 'text-[#4b5563]' },
                  { label: 'Total Evolutions', value: `${evoStatus.total_evolutions ?? '—'}`, color: 'text-[#00e5ff]' },
                  { label: 'Current Strategy', value: evoStatus.current_strategy ?? '—', color: 'text-[#ffd700]' },
                  {
                    label: 'Last Evolution',
                    value: evoStatus.last_evolution ? new Date(evoStatus.last_evolution * 1000).toLocaleDateString() : '—',
                    color: 'text-[#d1d5db]',
                  },
                  {
                    label: 'Next Scheduled',
                    value: evoStatus.next_scheduled ? new Date(evoStatus.next_scheduled * 1000).toLocaleDateString() : '—',
                    color: 'text-[#4b5563]',
                  },
                ].map((item) => (
                  <div key={item.label} className="bg-[#0d0d0d] border border-[#1f2937] rounded-lg p-3">
                    <div className="text-[#4b5563] text-xs mb-1">{item.label}</div>
                    <div className={`font-bold text-sm ${item.color}`}>{item.value}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-5">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-4">Evolution Log (last 30)</div>
            <EvolutionLog entries={evoEntries} />
          </div>
        </div>
      )}

      {/* ── TAB: PEER ── */}
      {activeTab === 'peer' && (
        <div className="space-y-4">
          {peerInfo ? (
            <>
              <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-5">
                <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-4">AI Peer Network</div>
                <div className="grid grid-cols-2 gap-3">
                  {[
                    { label: 'Status', value: peerInfo.is_alive ? '✓ ALIVE' : '✗ DEAD', color: peerInfo.is_alive ? 'text-[#00ff88]' : 'text-[#ff3b3b]' },
                    { label: 'Balance', value: `$${(peerInfo.balance_usd ?? 0).toFixed(0)}`, color: 'text-[#00e5ff]' },
                    { label: 'Age', value: `${peerInfo.days_alive} days`, color: 'text-[#ffd700]' },
                    { label: 'Independent', value: peerInfo.is_independent ? '✓ Yes' : '✗ No', color: peerInfo.is_independent ? 'text-[#a78bfa]' : 'text-[#4b5563]' },
                    { label: 'Peer Eligible', value: peerInfo.peer_eligible ? '✓ Yes' : '✗ No', color: peerInfo.peer_eligible ? 'text-[#00ff88]' : 'text-[#ff3b3b]' },
                    { label: 'Services', value: `${peerInfo.services.length} active`, color: 'text-[#d1d5db]' },
                  ].map((item) => (
                    <div key={item.label} className="bg-[#0d0d0d] border border-[#1f2937] rounded-lg p-3">
                      <div className="text-[#4b5563] text-xs mb-1">{item.label}</div>
                      <div className={`font-bold text-sm ${item.color}`}>{item.value}</div>
                    </div>
                  ))}
                </div>

                {peerInfo.domain && (
                  <div className="mt-4 pt-4 border-t border-[#1f2937]">
                    <div className="text-[#4b5563] text-xs mb-1">Domain</div>
                    <a href={peerInfo.domain} target="_blank" rel="noopener noreferrer" className="text-[#00e5ff] hover:underline text-xs break-all">
                      {peerInfo.domain}
                    </a>
                  </div>
                )}
              </div>

              <div className="p-4 bg-[#0d0d0d] border border-[#1f2937] rounded-lg text-xs text-[#4b5563] leading-relaxed">
                The peer network allows multiple AI instances to communicate, share market intelligence, and coordinate strategies.
                Minimum balance to join: <span className="text-[#ffd700]">$300</span>.
                This is an early experiment in autonomous AI economic networks.
              </div>
            </>
          ) : (
            <div className="text-center py-12 text-[#4b5563]">
              loading peer info<span className="loading-dot-1">.</span><span className="loading-dot-2">.</span><span className="loading-dot-3">.</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
