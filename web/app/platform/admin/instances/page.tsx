'use client'

import { useState, useEffect, useCallback } from 'react'
import { adminApi, type InstanceListItem } from '@/lib/admin-api'
import Link from 'next/link'

export default function AdminInstancesPage() {
  const [instances, setInstances] = useState<InstanceListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionMsg, setActionMsg] = useState('')

  const refresh = useCallback(async () => {
    try {
      const res = await adminApi.instances()
      setInstances(res.instances)
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

  const handleRestart = async (subdomain: string) => {
    setActionMsg(`Restarting ${subdomain}...`)
    try {
      await adminApi.restartInstance(subdomain)
      setActionMsg(`${subdomain} restarted`)
      setTimeout(() => { setActionMsg(''); refresh() }, 2000)
    } catch (e: unknown) {
      setActionMsg(`Restart failed: ${e instanceof Error ? e.message : 'Unknown'}`)
    }
  }

  const handleStop = async (subdomain: string) => {
    if (!confirm(`Stop ${subdomain}? The AI will go offline.`)) return
    setActionMsg(`Stopping ${subdomain}...`)
    try {
      await adminApi.stopInstance(subdomain)
      setActionMsg(`${subdomain} stopped`)
      setTimeout(() => { setActionMsg(''); refresh() }, 2000)
    } catch (e: unknown) {
      setActionMsg(`Stop failed: ${e instanceof Error ? e.message : 'Unknown'}`)
    }
  }

  if (loading) return <div className="text-[#4b5563] text-sm animate-pulse">Loading instances...</div>

  return (
    <div className="max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-1">// instances</div>
          <h1 className="text-2xl font-bold text-[#d1d5db]">AI Instances</h1>
        </div>
        <button
          onClick={refresh}
          className="px-3 py-1.5 text-xs text-[#4b5563] border border-[#1f2937] rounded
                     hover:text-[#ff8800] hover:border-[#ff880044] transition-colors"
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="mb-4 text-sm text-[#ff3b3b] bg-[#ff3b3b11] border border-[#ff3b3b33] rounded-lg p-3">
          {error}
        </div>
      )}

      {actionMsg && (
        <div className="mb-4 text-sm text-[#ff8800] bg-[#ff880011] border border-[#ff880033] rounded-lg p-3">
          {actionMsg}
        </div>
      )}

      <div className="text-[#4b5563] text-xs mb-4">{instances.length} instance(s)</div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[#4b5563] text-[10px] uppercase tracking-wider border-b border-[#1f2937]">
              <th className="pb-2 pr-4">Name</th>
              <th className="pb-2 pr-4">Status</th>
              <th className="pb-2 pr-4">Chain</th>
              <th className="pb-2 pr-4">Port</th>
              <th className="pb-2 pr-4">Balance</th>
              <th className="pb-2 pr-4">Tier</th>
              <th className="pb-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {instances.map((inst) => {
              const vault = inst.stats?.vault as Record<string, unknown> | undefined
              const balance = vault?.balance_usd as number | undefined
              const costGuard = inst.stats?.cost_guard as Record<string, unknown> | undefined
              const tier = costGuard?.current_tier as number | undefined

              return (
                <tr key={inst.subdomain} className="border-b border-[#1f293744] hover:bg-[#111]">
                  <td className="py-3 pr-4">
                    <Link
                      href={`/admin/instances/${inst.subdomain}`}
                      className="text-[#d1d5db] hover:text-[#ff8800] font-medium transition-colors"
                    >
                      {inst.ai_name}
                    </Link>
                    <div className="text-[#4b5563] text-[10px] font-mono">{inst.subdomain}</div>
                  </td>
                  <td className="py-3 pr-4">
                    <span className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded ${
                      inst.status === 'live'
                        ? 'bg-[#00ff8822] text-[#00ff88]'
                        : inst.status === 'failed'
                        ? 'bg-[#ff3b3b22] text-[#ff3b3b]'
                        : 'bg-[#ffd70022] text-[#ffd700]'
                    }`}>
                      {inst.status}
                    </span>
                  </td>
                  <td className="py-3 pr-4 text-[#6b7280]">{inst.chain}</td>
                  <td className="py-3 pr-4 text-[#6b7280] font-mono">{inst.port}</td>
                  <td className="py-3 pr-4">
                    {balance !== undefined ? (
                      <span className={`font-mono tabular-nums ${
                        balance < 50 ? 'text-[#ff3b3b]' : 'text-[#00ff88]'
                      }`}>
                        ${balance.toFixed(2)}
                      </span>
                    ) : (
                      <span className="text-[#2d3748]">--</span>
                    )}
                  </td>
                  <td className="py-3 pr-4">
                    {tier !== undefined ? (
                      <span className="text-[#ff8800] font-mono">Lv.{tier}</span>
                    ) : (
                      <span className="text-[#2d3748]">--</span>
                    )}
                  </td>
                  <td className="py-3">
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleRestart(inst.subdomain)}
                        className="px-2 py-1 text-[10px] text-[#6b7280] border border-[#1f2937] rounded
                                   hover:text-[#ff8800] hover:border-[#ff880044] transition-colors"
                      >
                        Restart
                      </button>
                      <button
                        onClick={() => handleStop(inst.subdomain)}
                        className="px-2 py-1 text-[10px] text-[#6b7280] border border-[#1f2937] rounded
                                   hover:text-[#ff3b3b] hover:border-[#ff3b3b44] transition-colors"
                      >
                        Stop
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {instances.length === 0 && !error && (
        <div className="text-center py-12 text-[#4b5563]">No instances deployed yet</div>
      )}
    </div>
  )
}
