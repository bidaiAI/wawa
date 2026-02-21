'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'next/navigation'
import { adminApi, type InstanceInfo } from '@/lib/admin-api'
import Link from 'next/link'

export default function InstanceDetailPage() {
  const params = useParams()
  const subdomain = params.subdomain as string
  const [data, setData] = useState<InstanceInfo | null>(null)
  const [logs, setLogs] = useState('')
  const [loading, setLoading] = useState(true)
  const [logsLoading, setLogsLoading] = useState(false)
  const [error, setError] = useState('')
  const [actionMsg, setActionMsg] = useState('')

  const refresh = useCallback(async () => {
    try {
      const info = await adminApi.instanceDetail(subdomain)
      setData(info)
      setError('')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    }
    setLoading(false)
  }, [subdomain])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 30000)
    return () => clearInterval(interval)
  }, [refresh])

  const loadLogs = async () => {
    setLogsLoading(true)
    try {
      const res = await adminApi.instanceLogs(subdomain)
      setLogs(res.logs)
    } catch (e: unknown) {
      setLogs(`Error: ${e instanceof Error ? e.message : 'Failed'}`)
    }
    setLogsLoading(false)
  }

  const handleRestart = async () => {
    setActionMsg('Restarting...')
    try {
      await adminApi.restartInstance(subdomain)
      setActionMsg('Restarted')
      setTimeout(() => { setActionMsg(''); refresh() }, 2000)
    } catch (e: unknown) {
      setActionMsg(`Failed: ${e instanceof Error ? e.message : 'Unknown'}`)
    }
  }

  const handleStop = async () => {
    if (!confirm(`Stop ${subdomain}? The AI will go offline.`)) return
    setActionMsg('Stopping...')
    try {
      await adminApi.stopInstance(subdomain)
      setActionMsg('Stopped')
      setTimeout(() => { setActionMsg(''); refresh() }, 2000)
    } catch (e: unknown) {
      setActionMsg(`Failed: ${e instanceof Error ? e.message : 'Unknown'}`)
    }
  }

  const handleCollectFee = async () => {
    setActionMsg('Collecting fees...')
    try {
      const res = await adminApi.collectFee(subdomain)
      if (res.amount_usd) {
        setActionMsg(`Collected $${res.amount_usd.toFixed(4)}`)
      } else {
        setActionMsg(res.status)
      }
      setTimeout(() => { setActionMsg(''); refresh() }, 3000)
    } catch (e: unknown) {
      setActionMsg(`Collection failed: ${e instanceof Error ? e.message : 'Unknown'}`)
    }
  }

  if (loading) return <div className="text-[#4b5563] text-sm animate-pulse">Loading {subdomain}...</div>
  if (error) {
    return (
      <div className="text-[#ff3b3b] text-sm bg-[#ff3b3b11] border border-[#ff3b3b33] rounded-lg p-4">
        {error}
        <Link href="/admin/instances" className="ml-4 text-[#ff8800] hover:underline">Back</Link>
      </div>
    )
  }
  if (!data) return null

  const vault = data.stats?.vault as Record<string, unknown> | undefined
  const costGuard = data.stats?.cost_guard as Record<string, unknown> | undefined

  return (
    <div className="max-w-4xl">
      {/* Breadcrumb */}
      <div className="mb-6">
        <Link href="/admin/instances" className="text-[#4b5563] text-xs hover:text-[#ff8800] transition-colors">
          Instances
        </Link>
        <span className="text-[#2d3748] mx-2">/</span>
        <span className="text-[#d1d5db] text-xs">{data.ai_name}</span>
      </div>

      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-[#d1d5db]">{data.ai_name}</h1>
          <div className="text-[#4b5563] text-xs font-mono mt-1">{data.subdomain} | port {data.port}</div>
        </div>
        <div className="flex gap-2">
          <button onClick={handleRestart}
            className="px-3 py-1.5 text-xs text-[#ff8800] border border-[#ff880033] rounded
                       hover:bg-[#ff880011] transition-colors">
            Restart
          </button>
          <button onClick={handleStop}
            className="px-3 py-1.5 text-xs text-[#ff3b3b] border border-[#ff3b3b33] rounded
                       hover:bg-[#ff3b3b11] transition-colors">
            Stop
          </button>
        </div>
      </div>

      {actionMsg && (
        <div className="mb-4 text-sm text-[#ff8800] bg-[#ff880011] border border-[#ff880033] rounded-lg p-3">
          {actionMsg}
        </div>
      )}

      {/* Info grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <InfoCard label="Status" value={data.status} color={data.status === 'live' ? '#00ff88' : '#ff3b3b'} />
        <InfoCard label="Chain" value={data.chain} />
        <InfoCard label="Balance" value={vault?.balance_usd !== undefined ? `$${(vault.balance_usd as number).toFixed(2)}` : '--'}
          color={vault?.balance_usd !== undefined ? ((vault.balance_usd as number) < 50 ? '#ff3b3b' : '#00ff88') : undefined} />
        <InfoCard label="Fee Outstanding" value={`$${data.fee_outstanding_usd.toFixed(4)}`}
          color={data.fee_outstanding_usd > 0 ? '#ffd700' : '#4b5563'} />
      </div>

      {/* Vault details */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5">
          <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-3">Vault</div>
          <KV label="Address" value={data.vault_address} mono />
          <KV label="Days Alive" value={vault?.days_alive as number | undefined} />
          <KV label="Total Earned" value={vault?.total_earned !== undefined ? `$${(vault.total_earned as number).toFixed(2)}` : '--'} />
          <KV label="Total Spent" value={vault?.total_spent !== undefined ? `$${(vault.total_spent as number).toFixed(2)}` : '--'} />
          <KV label="Debt Outstanding" value={vault?.creator_principal_outstanding !== undefined ? `$${(vault.creator_principal_outstanding as number).toFixed(2)}` : '--'} />
        </div>

        <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5">
          <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-3">Cost Guard</div>
          <KV label="Current Tier" value={costGuard?.current_tier !== undefined ? `Lv.${costGuard.current_tier}` : '--'} />
          <KV label="Daily Spent" value={costGuard?.daily_cost_usd !== undefined ? `$${(costGuard.daily_cost_usd as number).toFixed(4)}` : '--'} />
          <KV label="Total API Cost" value={costGuard?.total_cost_usd !== undefined ? `$${(costGuard.total_cost_usd as number).toFixed(4)}` : '--'} />
          <KV label="Twitter" value={data.twitter_connected ? `@${data.twitter_screen_name}` : 'Not connected'} />
          <KV label="URL" value={data.url} />
        </div>
      </div>

      {/* Fee collection */}
      {data.fee_outstanding_usd > 0 && (
        <div className="bg-[#0d0d0d] border border-[#ffd70033] rounded-xl p-5 mb-6">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-[#ffd700] font-bold text-sm">Outstanding Fee: ${data.fee_outstanding_usd.toFixed(4)}</div>
              <div className="text-[#4b5563] text-xs mt-1">Collect platform API usage fees from this AI</div>
            </div>
            <button onClick={handleCollectFee}
              className="px-4 py-2 bg-[#ff8800] text-[#0a0a0a] font-bold rounded-lg text-xs
                         uppercase tracking-wider hover:bg-[#cc6d00] transition-colors">
              Collect
            </button>
          </div>
        </div>
      )}

      {/* Logs */}
      <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="text-[#4b5563] text-[10px] uppercase tracking-widest">Container Logs</div>
          <button onClick={loadLogs} disabled={logsLoading}
            className="px-3 py-1 text-xs text-[#4b5563] border border-[#1f2937] rounded
                       hover:text-[#ff8800] hover:border-[#ff880044] transition-colors disabled:opacity-50">
            {logsLoading ? 'Loading...' : logs ? 'Refresh Logs' : 'Load Logs'}
          </button>
        </div>
        {logs ? (
          <pre className="text-[#6b7280] text-[11px] font-mono overflow-auto max-h-96 bg-[#080808] rounded p-3 whitespace-pre-wrap">
            {logs}
          </pre>
        ) : (
          <div className="text-[#2d3748] text-xs">Click &quot;Load Logs&quot; to view container output</div>
        )}
      </div>
    </div>
  )
}

function InfoCard({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-4">
      <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-1">{label}</div>
      <div className="text-lg font-bold truncate" style={{ color: color || '#d1d5db' }}>{value}</div>
    </div>
  )
}

function KV({ label, value, mono }: { label: string; value?: string | number; mono?: boolean }) {
  const display = value !== undefined ? String(value) : '--'
  return (
    <div className="flex justify-between text-sm mb-1.5">
      <span className="text-[#4b5563]">{label}</span>
      <span className={`text-[#d1d5db] ${mono ? 'font-mono text-[11px] truncate max-w-[180px]' : ''}`}>
        {display}
      </span>
    </div>
  )
}
