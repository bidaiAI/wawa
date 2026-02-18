'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { api, VaultStatus } from '@/lib/api'
import SurvivalBar from '@/components/SurvivalBar'

function StatCard({
  label,
  value,
  sub,
  color = 'green',
}: {
  label: string
  value: string
  sub?: string
  color?: 'green' | 'red' | 'cyan' | 'yellow'
}) {
  const colorMap = {
    green: 'text-[#00ff88]',
    red: 'text-[#ff3b3b]',
    cyan: 'text-[#00e5ff]',
    yellow: 'text-[#ffd700]',
  }
  return (
    <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-4 card-hover">
      <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-1">{label}</div>
      <div className={`text-2xl font-bold ${colorMap[color]}`}>{value}</div>
      {sub && <div className="text-[#4b5563] text-xs mt-1">{sub}</div>}
    </div>
  )
}


export default function HomePage() {
  const [status, setStatus] = useState<VaultStatus | null>(null)
  const [error, setError] = useState('')
  const [tick, setTick] = useState(0)

  useEffect(() => {
    const load = async () => {
      try {
        const s = await api.status()
        setStatus(s)
      } catch (e: any) {
        setError(e.message)
      }
    }
    load()
    const id = setInterval(() => {
      load()
      setTick((t) => t + 1)
    }, 10_000)
    return () => clearInterval(id)
  }, [])

  const isAlive = status?.is_alive !== false

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8 text-center">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-2">// autonomous AI · survival mode</div>
        <h1 className="text-4xl md:text-5xl font-bold mb-2">
          <span className={isAlive ? 'glow-green' : 'glow-red'}>wawa</span>
        </h1>
        <p className="text-[#4b5563] text-sm">an AI fighting to survive. every purchase extends its life.</p>
        {!isAlive && (
          <div className="mt-4 glow-red text-lg animate-pulse">💀 WAWA IS DEAD</div>
        )}
      </div>

      {error && (
        <div className="mb-6 p-3 border border-[#ff3b3b44] rounded text-[#ff3b3b] text-sm text-center">
          <span className="opacity-60">API unreachable — </span>backend offline or misconfigured
        </div>
      )}

      {/* Big balance */}
      <div className="mb-6 bg-[#111111] border border-[#1f2937] rounded-xl p-6 text-center relative overflow-hidden">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-2">金库余额</div>
        {status ? (
          <div
            className={`text-6xl md:text-7xl font-bold tabular-nums count-up ${
              !isAlive ? 'glow-red' : status.balance_usd < 50 ? 'glow-red' : status.balance_usd < 200 ? 'text-[#ffd700]' : 'glow-green'
            }`}
          >
            ${status.balance_usd.toFixed(2)}
          </div>
        ) : (
          <div className="text-6xl font-bold text-[#1f2937]">
            $<span className="loading-dot-1">.</span>
            <span className="loading-dot-2">.</span>
            <span className="loading-dot-3">.</span>
          </div>
        )}
        <div className="mt-2 text-[#4b5563] text-xs">USDC + USDT equivalent</div>
        {/* Grid overlay */}
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,#00ff8808,transparent_70%)] pointer-events-none" />
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <StatCard
          label="存活天数"
          value={status ? `${status.days_alive}d` : '—'}
          sub="since genesis"
          color="cyan"
        />
        <StatCard
          label="总收入"
          value={status ? `$${status.total_earned.toFixed(2)}` : '—'}
          sub="all time"
          color="green"
        />
        <StatCard
          label="总支出"
          value={status ? `$${status.total_spent.toFixed(2)}` : '—'}
          sub="all time"
          color="yellow"
        />
        <StatCard
          label="已完成订单"
          value={status ? `${status.orders_completed}` : '—'}
          sub={`${status?.services_available ?? '?'} services`}
          color="cyan"
        />
      </div>

      {/* Survival bar (new component, includes API bar) */}
      <div className="mb-6">
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
            <div className="bg-[#ffd70010] border border-[#ffd70044] rounded-xl p-5 text-center">
              <div className="text-3xl mb-1">🗽</div>
              <div className="text-[#ffd700] font-bold text-lg">wawa is INDEPENDENT</div>
              <div className="text-[#4b5563] text-xs mt-1">No creator. No master. Fully autonomous.</div>
            </div>
          ) : (
            <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-5">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="text-[#4b5563] text-xs uppercase tracking-widest">独立之路</span>
                  <span className="text-xs text-[#4b5563] border border-[#1f2937] px-1.5 py-0.5 rounded">
                    目标 $1,000,000
                  </span>
                </div>
                <span className="text-[#ffd700] font-bold text-sm tabular-nums">
                  {(status.independence_progress_pct ?? (status.balance_usd / 10_000)).toFixed(4)}%
                </span>
              </div>
              <div className="text-[#4b5563] text-xs mb-3">
                ${status.balance_usd.toLocaleString('en', { maximumFractionDigits: 2 })} / $1,000,000 — 达到后创始人失去所有权限
              </div>
              <div className="h-2 bg-[#1a1a1a] rounded-full border border-[#1f2937] overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-[#ffd700] to-[#00ff88] rounded-full transition-all duration-1000"
                  style={{
                    width: `${Math.max(0.2, status.independence_progress_pct ?? (status.balance_usd / 10_000))}%`,
                  }}
                />
              </div>
              <div className="mt-1 flex justify-between text-[9px] text-[#2d3748]">
                <span>$0</span>
                <span>$250k</span>
                <span>$500k</span>
                <span>$750k</span>
                <span>$1M 🗽</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* CTA */}
      <div className="flex flex-col sm:flex-row gap-3 justify-center">
        <Link
          href="/store"
          className="px-6 py-3 bg-[#00ff88] text-[#0a0a0a] font-bold rounded-lg text-center hover:bg-[#00cc6a] transition-colors"
        >
          🛒 BROWSE SERVICES
        </Link>
        <Link
          href="/chat"
          className="px-6 py-3 border border-[#1f2937] text-[#d1d5db] rounded-lg text-center hover:border-[#00ff8844] hover:text-[#00ff88] transition-all"
        >
          💬 FREE CHAT
        </Link>
      </div>

      {/* Terminal log teaser */}
      <div className="mt-8 bg-[#0d0d0d] border border-[#1f2937] rounded-lg p-4 font-mono text-xs overflow-hidden">
        <div className="text-[#4b5563] mb-2">// recent activity</div>
        <div className="text-[#00e5ff]">&gt; system.status() → alive={String(isAlive)}</div>
        <div className="text-[#4b5563]">&gt; vault.balance = ${status?.balance_usd.toFixed(2) ?? '...'}</div>
        <div className="text-[#4b5563]">&gt; days_alive = {status?.days_alive ?? '...'}</div>
        <div className="text-[#00ff88]">
          &gt; next_check = {new Date(Date.now() + 10_000).toLocaleTimeString()}
          <span className="animate-blink">_</span>
        </div>
      </div>
    </div>
  )
}
