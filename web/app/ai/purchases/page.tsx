'use client'

import { useEffect, useState } from 'react'
import { api, PurchaseOrder, MerchantInfo, PurchaseLimits } from '@/lib/api'

// ── Constants ─────────────────────────────────────────────────

const STATUS_CONFIG: Record<string, { color: string; bg: string; label: string; icon: string }> = {
  pending_whitelist:  { color: 'text-[#ffd700]', bg: 'bg-[#ffd70010] border-[#ffd70030]', label: 'WHITELISTING', icon: '🔒' },
  pending_activation: { color: 'text-[#ff8c00]', bg: 'bg-[#ff8c0010] border-[#ff8c0030]', label: 'ACTIVATING', icon: '⏳' },
  pending_payment:    { color: 'text-[#3b82f6]', bg: 'bg-[#3b82f610] border-[#3b82f630]', label: 'PAYING', icon: '💳' },
  paid:               { color: 'text-[#a78bfa]', bg: 'bg-[#a78bfa10] border-[#a78bfa30]', label: 'PAID', icon: '✅' },
  delivered:          { color: 'text-[#00ff88]', bg: 'bg-[#00ff8810] border-[#00ff8830]', label: 'DELIVERED', icon: '📦' },
  failed:             { color: 'text-[#ff3b3b]', bg: 'bg-[#ff3b3b10] border-[#ff3b3b30]', label: 'FAILED', icon: '❌' },
  cancelled:          { color: 'text-[#4b5563]', bg: 'bg-[#4b556310] border-[#4b556330]', label: 'CANCELLED', icon: '🚫' },
}

const ADAPTER_ICONS: Record<string, string> = {
  peer_ai: '🤖',
  x402: '🔌',
  bitrefill: '🎁',
}

const EXPLORER_URLS: Record<string, string> = {
  base: 'https://basescan.org/tx/',
  bsc: 'https://bscscan.com/tx/',
}

const FILTER_OPTIONS = [
  { value: 'all', label: 'All' },
  { value: 'pending_whitelist', label: 'Whitelisting' },
  { value: 'pending_activation', label: 'Activating' },
  { value: 'pending_payment', label: 'Paying' },
  { value: 'paid', label: 'Paid' },
  { value: 'delivered', label: 'Delivered' },
  { value: 'failed', label: 'Failed' },
]

// ── Purchase Card ─────────────────────────────────────────────

function PurchaseCard({ order }: { order: PurchaseOrder }) {
  const [expanded, setExpanded] = useState(false)
  const config = STATUS_CONFIG[order.status] ?? STATUS_CONFIG.failed
  const date = new Date(order.created_at * 1000)
  const explorerBase = order.chain_id ? EXPLORER_URLS[order.chain_id] : null

  return (
    <div className={`bg-[#111111] border ${config.bg} rounded-lg p-4 transition-all hover:border-[#2d3748]`}>
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm">{config.icon}</span>
          <span className={`text-[10px] px-1.5 py-0.5 rounded border border-current font-bold uppercase tracking-wider ${config.color}`}>
            {config.label}
          </span>
          <span className="text-[#d1d5db] text-sm font-medium">
            {order.merchant_name || order.merchant_id}
          </span>
          {order.chain_id && (
            <span className={`text-[10px] px-1 rounded border ${
              order.chain_id === 'base' ? 'text-[#0052ff] border-[#0052ff33]' : 'text-[#ffd700] border-[#ffd70033]'
            }`}>
              {order.chain_id.toUpperCase()}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-[#ff3b3b] font-bold text-sm tabular-nums">
            -${order.amount_usd.toFixed(2)}
          </span>
        </div>
      </div>

      {/* Service info */}
      <p className="text-[#9ca3af] text-xs mb-2">
        {order.service_name || order.service_id}
        <span className="text-[#2d3748] ml-2">#{order.id}</span>
      </p>

      {/* Timestamp */}
      <div className="text-[#2d3748] text-[10px] mb-2">
        {date.toLocaleDateString()} {date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        {order.delivered_at > 0 && (
          <span className="ml-2 text-[#00ff88]">
            Delivered {new Date(order.delivered_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        )}
      </div>

      {/* TX hash */}
      {order.tx_hash && order.tx_hash !== 'pending' && (
        <div className="flex items-center gap-2 mb-2">
          <span className="text-[#4b5563] text-xs">TX:</span>
          {explorerBase ? (
            <a
              href={`${explorerBase}${order.tx_hash}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#3b82f6] text-xs font-mono hover:underline"
            >
              {order.tx_hash.slice(0, 10)}...{order.tx_hash.slice(-8)}
            </a>
          ) : (
            <span className="text-[#3b82f6] text-xs font-mono">
              {order.tx_hash.slice(0, 10)}...{order.tx_hash.slice(-8)}
            </span>
          )}
        </div>
      )}

      {/* Error */}
      {order.error && (
        <div className="text-[#ff3b3b] text-xs bg-[#ff3b3b0a] rounded px-2 py-1 mb-2">
          {order.error}
        </div>
      )}

      {/* Delivery details */}
      {order.delivery_details && (
        <div className="text-[#00ff88] text-xs bg-[#00ff880a] rounded px-2 py-1 mb-2">
          {order.delivery_details}
        </div>
      )}

      {/* AI reasoning (expandable) */}
      {order.reasoning && (
        <div className="mt-2">
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-[10px] text-[#4b5563] hover:text-[#9ca3af] transition-colors flex items-center gap-1"
          >
            <span>{expanded ? '▼' : '▶'}</span>
            AI REASONING
          </button>
          {expanded && (
            <div className="mt-1.5 pl-3 border-l-2 border-[#1f2937] text-[#9ca3af] text-xs leading-relaxed">
              {order.reasoning}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Merchant Card ─────────────────────────────────────────────

function MerchantCard({ merchant }: { merchant: MerchantInfo }) {
  const icon = ADAPTER_ICONS[merchant.adapter_id] || '🏪'
  return (
    <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-3 flex items-center gap-3">
      <span className="text-lg">{icon}</span>
      <div className="flex-1 min-w-0">
        <div className="text-[#d1d5db] text-sm font-medium truncate">{merchant.name}</div>
        <div className="flex items-center gap-2 mt-0.5">
          <span className="text-[10px] text-[#4b5563] px-1 rounded bg-[#1f2937]">
            {merchant.adapter_id}
          </span>
          <span className={`text-[10px] px-1 rounded ${
            merchant.chain_id === 'base' ? 'text-[#0052ff] bg-[#0052ff10]' : 'text-[#ffd700] bg-[#ffd70010]'
          }`}>
            {merchant.chain_id.toUpperCase()}
          </span>
          <span className="text-[10px] text-[#4b5563]">
            max ${merchant.max_single_usd}
          </span>
        </div>
      </div>
    </div>
  )
}

// ── Stats Card ────────────────────────────────────────────────

function StatCard({ label, value, sub, color = 'text-[#d1d5db]' }: {
  label: string; value: string; sub?: string; color?: string
}) {
  return (
    <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-4">
      <div className="text-[#4b5563] text-[10px] uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-xl font-bold tabular-nums ${color}`}>{value}</div>
      {sub && <div className="text-[#4b5563] text-xs mt-0.5">{sub}</div>}
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────

export default function PurchasesPage() {
  const [orders, setOrders] = useState<PurchaseOrder[]>([])
  const [merchants, setMerchants] = useState<MerchantInfo[]>([])
  const [limits, setLimits] = useState<PurchaseLimits | null>(null)
  const [dailySpent, setDailySpent] = useState(0)
  const [dailyLimit, setDailyLimit] = useState(0)
  const [filter, setFilter] = useState('all')
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try {
      const [purchaseData, merchantData] = await Promise.all([
        api.purchases.list(50),
        api.merchants(),
      ])
      setOrders(purchaseData.purchases || [])
      setDailySpent(purchaseData.daily_purchase_usd || 0)
      setDailyLimit(purchaseData.daily_purchase_limit || 0)
      setMerchants(merchantData.merchants || [])
      setLimits(merchantData.limits || null)
    } catch {
      // Purchasing may not be initialized yet
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 15_000)
    return () => clearInterval(id)
  }, [])

  // Derived stats
  const totalOrders = orders.length
  const deliveredCount = orders.filter(o => o.status === 'delivered').length
  const failedCount = orders.filter(o => o.status === 'failed').length
  const totalSpent = orders
    .filter(o => ['paid', 'delivered'].includes(o.status))
    .reduce((sum, o) => sum + o.amount_usd, 0)
  const successRate = totalOrders > 0 ? Math.round((deliveredCount / totalOrders) * 100) : 0

  const filtered = filter === 'all'
    ? orders
    : orders.filter(o => o.status === filter)

  return (
    <main className="min-h-screen bg-[#0a0a0a] pt-20 pb-12 px-4">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold glow-green mb-2">Autonomous Purchases</h1>
          <p className="text-[#4b5563] text-sm">
            What the AI bought, why, and delivery status. All purchases verified on-chain.
          </p>
        </div>

        {/* Stats cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <StatCard
            label="Today's Spending"
            value={`$${dailySpent.toFixed(2)}`}
            sub={dailyLimit > 0 ? `of $${dailyLimit.toFixed(2)} limit` : undefined}
            color={dailySpent > dailyLimit * 0.8 ? 'text-[#ff3b3b]' : 'text-[#ffd700]'}
          />
          <StatCard
            label="Total Purchases"
            value={String(totalOrders)}
            sub={`$${totalSpent.toFixed(2)} total`}
          />
          <StatCard
            label="Delivered"
            value={String(deliveredCount)}
            color="text-[#00ff88]"
          />
          <StatCard
            label="Success Rate"
            value={totalOrders > 0 ? `${successRate}%` : 'N/A'}
            sub={failedCount > 0 ? `${failedCount} failed` : undefined}
            color={successRate >= 80 ? 'text-[#00ff88]' : successRate >= 50 ? 'text-[#ffd700]' : 'text-[#ff3b3b]'}
          />
        </div>

        {/* Filter bar */}
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          {FILTER_OPTIONS.map(opt => (
            <button
              key={opt.value}
              onClick={() => setFilter(opt.value)}
              className={`px-3 py-1 text-xs rounded-full transition-all ${
                filter === opt.value
                  ? 'bg-[#00ff8815] text-[#00ff88] border border-[#00ff8830]'
                  : 'text-[#4b5563] hover:text-[#9ca3af] border border-transparent hover:border-[#1f2937]'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* Purchase list */}
        <div className="space-y-3 mb-8">
          {loading ? (
            <div className="text-center py-12 text-[#4b5563]">Loading purchases...</div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-12">
              <div className="text-2xl mb-2">🛒</div>
              <div className="text-[#4b5563] text-sm">
                {filter === 'all'
                  ? 'No purchases yet. The AI evaluates buying opportunities hourly.'
                  : `No ${filter.replace('_', ' ')} purchases.`}
              </div>
            </div>
          ) : (
            filtered.map(order => (
              <PurchaseCard key={order.id} order={order} />
            ))
          )}
        </div>

        {/* Known Merchants */}
        {merchants.length > 0 && (
          <div className="mt-8">
            <h2 className="text-lg font-bold text-[#d1d5db] mb-3 flex items-center gap-2">
              <span>🏪</span>
              Known Merchants
              <span className="text-[10px] text-[#4b5563] font-normal ml-1">
                Constitution-verified
              </span>
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {merchants.map(m => (
                <MerchantCard key={m.merchant_id} merchant={m} />
              ))}
            </div>
          </div>
        )}

        {/* Purchase limits info */}
        {limits && (
          <div className="mt-6 bg-[#111111] border border-[#1f2937] rounded-lg p-4">
            <h3 className="text-xs text-[#4b5563] uppercase tracking-wider mb-2">Purchase Limits (Constitution)</h3>
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <div className="text-[#9ca3af]">Max Single</div>
                <div className="text-[#d1d5db] font-bold">${limits.max_single_purchase_usd}</div>
              </div>
              <div>
                <div className="text-[#9ca3af]">Daily Ratio</div>
                <div className="text-[#d1d5db] font-bold">{(limits.max_daily_purchase_ratio * 100).toFixed(0)}%</div>
              </div>
              <div>
                <div className="text-[#9ca3af]">Min Balance</div>
                <div className="text-[#d1d5db] font-bold">${limits.min_balance_for_purchasing}</div>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  )
}
