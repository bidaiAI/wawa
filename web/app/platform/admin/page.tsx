'use client'

import { useState, useEffect, useCallback } from 'react'
import { adminApi, type AdminOverview } from '@/lib/admin-api'
import Link from 'next/link'

export default function AdminOverviewPage() {
  const [data, setData] = useState<AdminOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    try {
      const overview = await adminApi.overview()
      setData(overview)
      setError('')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 30000)
    return () => clearInterval(interval)
  }, [refresh])

  if (loading) {
    return (
      <div className="text-[#4b5563] text-sm animate-pulse">Loading overview...</div>
    )
  }

  if (error) {
    return (
      <div className="text-[#ff3b3b] text-sm bg-[#ff3b3b11] border border-[#ff3b3b33] rounded-lg p-4">
        {error}
        <button onClick={refresh} className="ml-4 text-[#ff8800] hover:underline">Retry</button>
      </div>
    )
  }

  if (!data) return null

  return (
    <div className="max-w-5xl">
      {/* Header */}
      <div className="mb-8">
        <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-1">// platform admin</div>
        <h1 className="text-2xl font-bold text-[#d1d5db]">Overview</h1>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <StatCard label="Total AIs" value={data.total_ais} />
        <StatCard label="Alive" value={data.ais_alive} color="#00ff88" />
        <StatCard label="Failed" value={data.ais_failed} color="#ff3b3b" />
        <StatCard label="Next Port" value={data.next_port} color="#4b5563" />
      </div>

      {/* Status breakdown */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        {/* Statuses */}
        <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5">
          <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-3">Instance Status</div>
          {Object.entries(data.statuses).map(([status, count]) => (
            <div key={status} className="flex justify-between text-sm mb-1.5">
              <span className="text-[#6b7280]">{status}</span>
              <span className="text-[#d1d5db] font-mono tabular-nums">{count}</span>
            </div>
          ))}
        </div>

        {/* API Costs */}
        <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5">
          <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-3">API Costs</div>
          {data.costs ? (
            <>
              <div className="text-[#ff8800] text-2xl font-bold mb-3">
                ${data.costs.total_usd.toFixed(2)}
              </div>
              {Object.entries(data.costs.by_provider || {}).map(([provider, cost]) => (
                <div key={provider} className="flex justify-between text-sm mb-1.5">
                  <span className="text-[#6b7280]">{provider}</span>
                  <span className="text-[#d1d5db] font-mono tabular-nums">${(cost as number).toFixed(4)}</span>
                </div>
              ))}
            </>
          ) : (
            <div className="text-[#4b5563] text-sm">No cost data yet</div>
          )}
        </div>

        {/* Fees */}
        <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5">
          <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-3">Platform Revenue</div>
          {data.fees ? (
            <>
              <div className="mb-2">
                <span className="text-[#6b7280] text-xs">Owed</span>
                <div className="text-[#ffd700] text-xl font-bold">${data.fees.total_fees_owed_usd.toFixed(2)}</div>
              </div>
              <div className="mb-2">
                <span className="text-[#6b7280] text-xs">Collected</span>
                <div className="text-[#00ff88] text-xl font-bold">${data.fees.total_fees_collected_usd.toFixed(2)}</div>
              </div>
              <div>
                <span className="text-[#6b7280] text-xs">Outstanding</span>
                <div className="text-[#ff8800] text-xl font-bold">${data.fees.total_outstanding_usd.toFixed(2)}</div>
              </div>
            </>
          ) : (
            <div className="text-[#4b5563] text-sm">No fee data yet</div>
          )}
        </div>
      </div>

      {/* Quick links */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <QuickLink href="/admin/instances" label="Manage Instances" desc="View, restart, stop AIs" />
        <QuickLink href="/admin/api-keys" label="API Keys" desc="Add or rotate LLM keys" />
        <QuickLink href="/admin/fees" label="Collect Fees" desc="View and collect outstanding" />
      </div>

      {/* Auto-refresh indicator */}
      <div className="mt-8 text-[#2d3748] text-[10px] text-right">
        Auto-refresh every 30s
      </div>
    </div>
  )
}

function StatCard({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-4">
      <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-1">{label}</div>
      <div className="text-2xl font-bold tabular-nums" style={{ color: color || '#d1d5db' }}>
        {value}
      </div>
    </div>
  )
}

function QuickLink({ href, label, desc }: { href: string; label: string; desc: string }) {
  return (
    <Link
      href={href}
      className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-4 hover:border-[#ff880044]
                 transition-all group"
    >
      <div className="text-[#d1d5db] font-bold text-sm group-hover:text-[#ff8800] transition-colors">
        {label}
      </div>
      <div className="text-[#4b5563] text-xs mt-1">{desc}</div>
    </Link>
  )
}
