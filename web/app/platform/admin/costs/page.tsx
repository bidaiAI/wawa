'use client'

import { useState, useEffect, useCallback } from 'react'
import { adminApi, type CostData, type CostHistoryEntry } from '@/lib/admin-api'

export default function AdminCostsPage() {
  const [costs, setCosts] = useState<CostData | null>(null)
  const [history, setHistory] = useState<CostHistoryEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [historyDays, setHistoryDays] = useState(7)

  const refresh = useCallback(async () => {
    try {
      const [costData, historyData] = await Promise.all([
        adminApi.costs(),
        adminApi.costHistory(historyDays),
      ])
      setCosts(costData)
      setHistory(historyData.history)
      setError('')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    }
    setLoading(false)
  }, [historyDays])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 30000)
    return () => clearInterval(interval)
  }, [refresh])

  if (loading) return <div className="text-[#4b5563] text-sm animate-pulse">Loading costs...</div>

  return (
    <div className="max-w-4xl">
      <div className="mb-8">
        <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-1">// costs</div>
        <h1 className="text-2xl font-bold text-[#d1d5db]">API Cost Tracking</h1>
        <p className="text-[#4b5563] text-xs mt-1">
          Real-time API costs across all providers and AI instances
        </p>
      </div>

      {error && (
        <div className="mb-4 text-sm text-[#ff3b3b] bg-[#ff3b3b11] border border-[#ff3b3b33] rounded-lg p-3">
          {error}
          <button onClick={refresh} className="ml-4 text-[#ff8800] hover:underline">Retry</button>
        </div>
      )}

      {costs && (
        <>
          {/* Total */}
          <div className="bg-[#0d0d0d] border border-[#ff880033] rounded-xl p-6 mb-6 text-center">
            <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-2">Total API Spend</div>
            <div className="text-[#ff8800] text-4xl font-bold tabular-nums">${costs.total_usd.toFixed(2)}</div>
            <div className="text-[#2d3748] text-[10px] mt-2">
              {costs.snapshot_count} snapshots | Last updated: {costs.last_updated ? new Date(costs.last_updated * 1000).toLocaleTimeString() : 'N/A'}
            </div>
          </div>

          {/* Provider breakdown */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5">
              <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-3">By Provider</div>
              {Object.entries(costs.by_provider).length > 0 ? (
                Object.entries(costs.by_provider)
                  .sort(([, a], [, b]) => b - a)
                  .map(([provider, cost]) => (
                    <div key={provider} className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: providerColor(provider) }} />
                        <span className="text-[#d1d5db] text-sm capitalize">{provider}</span>
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="w-24 h-1.5 bg-[#1f2937] rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full"
                            style={{
                              width: `${costs.total_usd > 0 ? (cost / costs.total_usd * 100) : 0}%`,
                              backgroundColor: providerColor(provider),
                            }}
                          />
                        </div>
                        <span className="text-[#6b7280] text-xs font-mono tabular-nums w-20 text-right">
                          ${cost.toFixed(4)}
                        </span>
                      </div>
                    </div>
                  ))
              ) : (
                <div className="text-[#4b5563] text-sm">No provider data yet</div>
              )}
            </div>

            <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5">
              <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-3">By AI</div>
              {Object.entries(costs.by_ai).length > 0 ? (
                Object.entries(costs.by_ai)
                  .sort(([, a], [, b]) => b - a)
                  .map(([ai, cost]) => (
                    <div key={ai} className="flex justify-between mb-2">
                      <span className="text-[#d1d5db] text-sm">{ai}</span>
                      <span className="text-[#6b7280] text-xs font-mono tabular-nums">${cost.toFixed(4)}</span>
                    </div>
                  ))
              ) : (
                <div className="text-[#4b5563] text-sm">No per-AI data yet</div>
              )}
            </div>
          </div>
        </>
      )}

      {/* History */}
      <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="text-[#4b5563] text-[10px] uppercase tracking-widest">Cost History</div>
          <div className="flex gap-2">
            {[7, 14, 30].map((d) => (
              <button
                key={d}
                onClick={() => setHistoryDays(d)}
                className={`px-2 py-1 text-[10px] rounded transition-colors ${
                  historyDays === d
                    ? 'text-[#ff8800] bg-[#ff880011] border border-[#ff880033]'
                    : 'text-[#4b5563] border border-[#1f2937] hover:text-[#d1d5db]'
                }`}
              >
                {d}d
              </button>
            ))}
          </div>
        </div>
        {history.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[#4b5563] text-[10px] uppercase tracking-wider border-b border-[#1f2937]">
                  <th className="pb-2 pr-4">Time</th>
                  <th className="pb-2 pr-4">Total</th>
                  <th className="pb-2">Providers</th>
                </tr>
              </thead>
              <tbody>
                {history.slice(-20).reverse().map((entry, i) => (
                  <tr key={i} className="border-b border-[#1f293744]">
                    <td className="py-2 pr-4 text-[#6b7280] text-xs">
                      {new Date(entry.timestamp * 1000).toLocaleString()}
                    </td>
                    <td className="py-2 pr-4 text-[#ff8800] font-mono tabular-nums">
                      ${entry.total_usd.toFixed(4)}
                    </td>
                    <td className="py-2 text-[#4b5563] text-xs">
                      {Object.entries(entry.by_provider)
                        .map(([p, c]) => `${p}: $${c.toFixed(4)}`)
                        .join(' | ')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-[#4b5563] text-sm text-center py-6">
            No history data yet. Cost snapshots are recorded periodically.
          </div>
        )}
      </div>
    </div>
  )
}

function providerColor(provider: string): string {
  const colors: Record<string, string> = {
    gemini: '#4285f4',
    deepseek: '#00d4aa',
    openrouter: '#ff6b6b',
    ollama: '#9b59b6',
  }
  return colors[provider.toLowerCase()] || '#6b7280'
}
