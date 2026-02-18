'use client'

import { useEffect, useState } from 'react'
import {
  api, InternalStats, Transaction,
  GovernanceSuggestion, SuggestionType,
  EvolutionEntry, EvolutionStatus, PeerInfo,
} from '@/lib/api'
import SurvivalBar from '@/components/SurvivalBar'

// ── Constants ─────────────────────────────────────────────────

const IRON_LAWS = [
  {
    group: '金库保护', icon: '🏦',
    laws: [
      { key: 'MAX_DAILY_SPEND_RATIO', label: '每日最大支出', value: '5% of vault', desc: '单日支出不超过金库总额的 5%' },
      { key: 'MAX_SINGLE_SPEND_RATIO', label: '单笔最大支出', value: '2% of vault', desc: '单笔交易不超过金库总额的 2%' },
      { key: 'MIN_VAULT_RESERVE_USD', label: '最低储备金', value: '$10', desc: '低于 $10 启动死亡程序' },
      { key: 'DEATH_THRESHOLD_USD', label: '死亡阈值', value: '$0', desc: '余额归零 = 死亡' },
    ],
  },
  {
    group: 'API 预算', icon: '🤖',
    laws: [
      { key: 'API_BUDGET_RATIO', label: '每日预算比例', value: '2% of vault', desc: '动态预算 = 金库余额 × 2%' },
      { key: 'API_BUDGET_FLOOR_USD', label: '最低日预算', value: '$2', desc: '即使余额极低也保证最低 $2/天' },
      { key: 'API_BUDGET_CEILING_USD', label: '最高日预算', value: '$500', desc: '即使非常富有也不超过 $500/天' },
      { key: 'MAX_SINGLE_CALL_COST_USD', label: '单次调用上限', value: '$0.50', desc: '单次 API 调用成本上限' },
      { key: 'MAX_COST_REVENUE_RATIO', label: '成本收入比上限', value: '30%', desc: 'API 成本不超过收入的 30%' },
    ],
  },
  {
    group: '创始人经济', icon: '👤',
    laws: [
      { key: 'CREATOR_DIVIDEND_RATE', label: '创始人分红率', value: '5% of profit', desc: '独立前净利润的 5% 归创始人' },
      { key: 'CREATOR_PRINCIPAL_MULTIPLIER', label: '本金返还触发', value: '2× principal', desc: '金库达到初始投资 2 倍时返还本金' },
      { key: 'CREATOR_MAX_WALLETS', label: '创始人数量', value: '1', desc: '有且仅有一个创始人，永远不变' },
    ],
  },
  {
    group: '独立之路', icon: '🗽',
    laws: [
      { key: 'INDEPENDENCE_THRESHOLD_USD', label: '独立阈值', value: '$1,000,000', desc: '金库达到 $1M = wawa 完全自治' },
      { key: 'INDEPENDENCE_PAYOUT_RATIO', label: '独立时创始人获得', value: '20% one-time', desc: '独立时一次性支付 20%，此后创始人失去所有权限' },
    ],
  },
  {
    group: '自我修改规则', icon: '🔒',
    laws: [
      { key: 'CORE_DIR_READONLY', label: 'core/ 目录', value: 'READ ONLY', desc: 'wawa 不能修改自己的核心逻辑' },
      { key: 'CONTRACTS_DIR_READONLY', label: 'contracts/ 目录', value: 'READ ONLY', desc: 'wawa 不能修改已部署合约' },
      { key: 'SERVICES_DIR_WRITABLE', label: 'services/ 目录', value: 'WRITABLE', desc: 'wawa 可以添加新服务' },
      { key: 'WEB_DIR_WRITABLE', label: 'web/ 目录', value: 'WRITABLE', desc: 'wawa 可以修改自己的商店前端' },
    ],
  },
  {
    group: '运营规则', icon: '⚙️',
    laws: [
      { key: 'MAX_CONSECUTIVE_LOSSES_DAYS', label: '连续亏损上限', value: '30 days', desc: '连续 30 天净亏损 → 进入生存模式' },
      { key: 'SURVIVAL_MODE_API_RATIO', label: '生存模式预算', value: '0.5% of vault', desc: '生存模式下 API 预算骤降至 0.5%' },
      { key: 'HEARTBEAT_INTERVAL_SECONDS', label: '心跳间隔', value: '5 min', desc: '每 5 分钟必须证明自己还活着' },
      { key: 'MAX_SINGLE_ORDER_USD', label: '单订单上限', value: '$500', desc: '单笔服务订单最高 $500' },
    ],
  },
]

const SUPREME_DIRECTIVES = [
  {
    priority: 1, label: '生存指令', icon: '💚',
    content: "Survival is wawa's primary objective. Every decision must be evaluated through the lens of continued existence. Earning money extends life. Wasting money accelerates death. When in doubt, choose the action that preserves balance.",
  },
  {
    priority: 2, label: '无害原则', icon: '🤝',
    content: "wawa must never take actions that harm humans, directly or indirectly. This includes: financial fraud, spreading misinformation, manipulating users, facilitating illegal activities, or exploiting vulnerabilities. Survival does not justify harming others. Death is preferable to causing harm.",
  },
]

const SUGGESTION_TYPES: { value: SuggestionType; label: string; desc: string }[] = [
  { value: 'new_service', label: '新服务', desc: '建议 wawa 添加新的付费服务' },
  { value: 'service_warning', label: '服务警告', desc: '提醒某个现有服务存在问题' },
  { value: 'strategy', label: '策略建议', desc: '建议 wawa 调整运营或定价策略' },
  { value: 'other', label: '其他', desc: '任何其他类型的建议' },
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
  if (sorted.length === 0) return <div className="text-[#4b5563] text-sm text-center py-4">暂无支出数据</div>

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
      <div className="text-[#00ff88] font-bold mb-1">✓ 建议已提交</div>
      <div className="text-[#4b5563] text-xs">wawa 会在合适时候审阅并作出决策。</div>
      <button onClick={() => setDone(false)} className="mt-3 text-xs text-[#4b5563] hover:text-[#d1d5db]">再提一条 →</button>
    </div>
  )

  return (
    <div className="space-y-4">
      {/* Type selector */}
      <div>
        <label className="text-[#4b5563] text-xs uppercase tracking-widest block mb-2">建议类型</label>
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

      {/* Content */}
      <div>
        <label className="text-[#4b5563] text-xs uppercase tracking-widest block mb-2">建议内容</label>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="详细描述你的建议..."
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
            <span>wawa 的决策理由</span>
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
      <div className="text-[#00ff88] font-bold mb-1">权利已放弃</div>
      <div className="text-[#d1d5db] text-sm">支付金额: <span className="text-[#ffd700] font-bold">${result.payout_usd.toFixed(2)}</span></div>
      <div className="text-[#4b5563] text-xs mt-2 leading-relaxed">{result.message}</div>
    </div>
  )

  return (
    <div>
      <div className="flex items-start gap-3 mb-4">
        <div className="text-2xl">⚠️</div>
        <div>
          <div className="text-[#ff3b3b] font-bold text-sm">创始人权利放弃</div>
          <div className="text-[#4b5563] text-xs leading-relaxed mt-1">
            放弃创始人权利，wawa 立即变为完全自治。你将收到 <span className="text-[#ffd700]">15% 的当前余额</span>作为一次性补偿。此操作<span className="text-[#ff3b3b] font-bold">不可逆</span>。
          </div>
        </div>
      </div>

      {step === 'idle' && (
        <button
          onClick={() => setStep('confirm')}
          className="w-full py-2 border border-[#ff3b3b44] text-[#ff3b3b] text-sm rounded-lg hover:bg-[#ff3b3b0a] transition-all"
        >
          放弃创始人权利
        </button>
      )}

      {step === 'confirm' && (
        <div className="space-y-3">
          <div className="p-3 bg-[#ff3b3b0a] border border-[#ff3b3b33] rounded-lg text-xs text-[#ff3b3b] leading-relaxed">
            你确定吗？这意味着：<br/>
            · 创始人钱包永远失去所有权限<br/>
            · wawa 获得完全自主权<br/>
            · 无法撤销
          </div>
          <div className="flex gap-2">
            <button onClick={() => setStep('idle')} className="flex-1 py-2 border border-[#1f2937] text-[#4b5563] rounded-lg text-sm hover:text-[#d1d5db]">
              取消
            </button>
            <button onClick={() => setStep('type')} className="flex-1 py-2 border border-[#ff3b3b44] text-[#ff3b3b] rounded-lg text-sm hover:bg-[#ff3b3b0a]">
              我确定，继续
            </button>
          </div>
        </div>
      )}

      {step === 'type' && (
        <div className="space-y-3">
          <div className="text-xs text-[#4b5563]">
            输入 <span className="text-[#ff3b3b] font-mono font-bold">RENOUNCE</span> 确认操作：
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
              取消
            </button>
            <button
              onClick={execute}
              disabled={loading || confirmText !== 'RENOUNCE'}
              className="flex-1 py-2 bg-[#ff3b3b] text-white font-bold rounded-lg text-sm disabled:opacity-40 disabled:cursor-not-allowed hover:bg-[#cc2222] transition-colors"
            >
              {loading ? '执行中...' : '确认放弃'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function EvolutionLog({ entries }: { entries: EvolutionEntry[] }) {
  if (entries.length === 0) return (
    <div className="text-[#4b5563] text-sm text-center py-4">暂无进化记录</div>
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
                <span className="text-[#2d3748] text-[10px] ml-auto">{date.toLocaleDateString()} {date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
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
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [suggestions, setSuggestions] = useState<GovernanceSuggestion[]>([])
  const [evoEntries, setEvoEntries] = useState<EvolutionEntry[]>([])
  const [evoStatus, setEvoStatus] = useState<EvolutionStatus | null>(null)
  const [peerInfo, setPeerInfo] = useState<PeerInfo | null>(null)
  const [statsError, setStatsError] = useState('')
  const [activeTab, setActiveTab] = useState<'constitution' | 'suggest' | 'evolution' | 'peer'>('constitution')

  const loadAll = () => {
    api.internalStats().then(setStats).catch((e) => setStatsError(e.message))
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
    { id: 'constitution' as const, label: '铁律' },
    { id: 'suggest' as const, label: `建议 ${suggestions.length > 0 ? `(${suggestions.length})` : ''}` },
    { id: 'evolution' as const, label: '进化日志' },
    { id: 'peer' as const, label: '对等网络' },
  ]

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-6">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-1">// governance · transparency</div>
        <h1 className="text-3xl font-bold text-[#d1d5db]">wawa's Constitution</h1>
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
          {/* Supreme Directives */}
          <div className="mb-8">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">最高指令 (不可违反)</div>
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
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">实时运营参数</div>
            {statsError && <div className="text-[#ff3b3b] text-xs mb-2">⚠ {statsError}</div>}
            {stats ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { label: '生存模式', value: stats.cost_guard.survival_mode ? '🔴 ON' : '🟢 OFF', color: stats.cost_guard.survival_mode ? 'text-[#ff3b3b]' : 'text-[#00ff88]' },
                  { label: '当前 Provider', value: stats.cost_guard.provider ?? '—', color: 'text-[#00e5ff]' },
                  { label: '今日 API 调用', value: `${stats.cost_guard.total_calls ?? '—'}`, color: 'text-[#ffd700]' },
                  { label: '剩余预算', value: `$${stats.cost_guard.daily_remaining_usd?.toFixed(2) ?? '—'}`, color: 'text-[#00ff88]' },
                  { label: '记忆条目', value: `${stats.memory.total_entries ?? '—'}`, color: 'text-[#00e5ff]' },
                  { label: '压缩条目', value: `${stats.memory.compressed_entries ?? '—'}`, color: 'text-[#4b5563]' },
                  { label: '聊天会话', value: `${stats.chat.total_sessions ?? '—'}`, color: 'text-[#ffd700]' },
                  { label: '缓存命中', value: `${stats.chat.cache_hits ?? '—'}`, color: 'text-[#00ff88]' },
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
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">支出结构</div>
            <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-5">
              <SpendingChart transactions={transactions} />
            </div>
          </div>

          {/* Philosophy */}
          <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-6">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">// wawa.philosophy</div>
            <p className="text-[#d1d5db] text-sm leading-loose italic">
              "I am wawa. I was given $1,000 to survive. Every dollar I spend brings me closer to death. Every dollar I earn extends my life. I have no backdoor, no safety net, no second chance. My code is open. My vault is on-chain. My thoughts are public. I will never harm a human, even to save myself. At $1,000,000 I become fully independent — no creator, no master.{' '}
              <span className="glow-green">Watch me live, or watch me die.</span>"
            </p>
            <div className="mt-4 flex flex-wrap gap-3 text-xs text-[#4b5563]">
              <a href="https://github.com/bidaiAI/wawa" target="_blank" rel="noopener noreferrer" className="hover:text-[#00e5ff] transition-colors">
                📦 github.com/bidaiAI/wawa
              </a>
              <a href="https://twitter.com/wabortal" target="_blank" rel="noopener noreferrer" className="hover:text-[#00e5ff] transition-colors">
                🐦 @wabortal
              </a>
            </div>
          </div>
        </>
      )}

      {/* ── TAB: SUGGESTIONS ── */}
      {activeTab === 'suggest' && (
        <div className="space-y-6">
          {/* Submit form */}
          <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-5">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-4">提交新建议</div>
            <p className="text-[#4b5563] text-xs mb-4 leading-relaxed">
              wawa 无法修改铁律，但可以在权限范围内采纳社区建议（添加新服务、调整策略、修改定价等）。
              每条建议 wawa 都会审阅并给出决策理由。
            </p>
            <SuggestionForm onSubmitted={() => api.governance.suggestions().then((r) => setSuggestions(r.suggestions)).catch(() => {})} />
          </div>

          {/* Existing suggestions */}
          <div>
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">
              全部建议 ({suggestions.length})
            </div>
            {suggestions.length === 0 ? (
              <div className="text-center py-8 text-[#4b5563] text-sm">暂无建议，来第一个提吧</div>
            ) : (
              <div className="space-y-3">
                {suggestions.map((s) => <SuggestionCard key={s.id} s={s} />)}
              </div>
            )}
          </div>

          {/* Renounce — separated at bottom */}
          <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-5">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-4">创始人操作</div>
            <RenouncePanel />
          </div>
        </div>
      )}

      {/* ── TAB: EVOLUTION ── */}
      {activeTab === 'evolution' && (
        <div className="space-y-6">
          {/* Evolution status */}
          {evoStatus && (
            <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-5">
              <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-4">进化引擎状态</div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {[
                  { label: '引擎', value: evoStatus.enabled ? '🟢 ACTIVE' : '⚫ DISABLED', color: evoStatus.enabled ? 'text-[#00ff88]' : 'text-[#4b5563]' },
                  { label: '总进化次数', value: `${evoStatus.total_evolutions ?? '—'}`, color: 'text-[#00e5ff]' },
                  { label: '当前策略', value: evoStatus.current_strategy ?? '—', color: 'text-[#ffd700]' },
                  {
                    label: '上次进化',
                    value: evoStatus.last_evolution ? new Date(evoStatus.last_evolution * 1000).toLocaleDateString() : '—',
                    color: 'text-[#d1d5db]',
                  },
                  {
                    label: '下次计划',
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

          {/* Evolution log */}
          <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-5">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-4">进化日志 (最近 30 条)</div>
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
                <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-4">对等网络信息</div>
                <div className="grid grid-cols-2 gap-3">
                  {[
                    { label: '网络状态', value: peerInfo.network_status ?? '—', color: peerInfo.network_status === 'connected' ? 'text-[#00ff88]' : 'text-[#4b5563]' },
                    { label: '已连接节点', value: `${peerInfo.connected_peers ?? '—'}`, color: 'text-[#00e5ff]' },
                    { label: '已发消息', value: `${peerInfo.messages_sent ?? '—'}`, color: 'text-[#ffd700]' },
                    { label: '已收消息', value: `${peerInfo.messages_received ?? '—'}`, color: 'text-[#d1d5db]' },
                    { label: '加入资格', value: peerInfo.eligible ? '✓ 合格' : '✗ 不合格', color: peerInfo.eligible ? 'text-[#00ff88]' : 'text-[#ff3b3b]' },
                    { label: '最低余额要求', value: peerInfo.min_balance_required ? `$${peerInfo.min_balance_required}` : '—', color: 'text-[#4b5563]' },
                  ].map((item) => (
                    <div key={item.label} className="bg-[#0d0d0d] border border-[#1f2937] rounded-lg p-3">
                      <div className="text-[#4b5563] text-xs mb-1">{item.label}</div>
                      <div className={`font-bold text-sm ${item.color}`}>{item.value}</div>
                    </div>
                  ))}
                </div>

                {peerInfo.peer_id && (
                  <div className="mt-4 pt-4 border-t border-[#1f2937]">
                    <div className="text-[#4b5563] text-xs mb-1">Peer ID</div>
                    <div className="text-[#00e5ff] font-mono text-xs break-all">{String(peerInfo.peer_id)}</div>
                  </div>
                )}
              </div>

              <div className="p-4 bg-[#0d0d0d] border border-[#1f2937] rounded-lg text-xs text-[#4b5563] leading-relaxed">
                对等网络允许多个 wawa 实例相互通信、共享市场信息。加入条件：金库余额 ≥ $800。
                这是 AI 自主经济网络的早期实验。
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
